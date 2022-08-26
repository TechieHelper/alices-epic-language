import re
import enum
import binascii
from sys import byteorder

class InstructionTypes(enum.Enum):
    FunctionStart = 1
    FunctionCall = 2
    FunctionEnd = 3
    VariableDef = 4
    VariableMod = 5
    VariableOperatorPlusEquals = 6


def parseLine(line):
    if "->" in line:  # function definition
        expr = "([a-zA-Z]*[0-9]+)([a-zA-Z][a-zA-Z0-9]*):(?:([a-zA-Z]*[0-9]+)([a-zA-Z][a-zA-Z0-9]*),)*(?:([a-zA-Z]*[0-9]+)([a-zA-Z][a-zA-Z0-9]*))?->{"
        matches = re.match(expr, line).groups()
        rtype = matches[0]
        funcname = matches[1]
        args = [*matches[2:]]
        for i in range(len(args)-1, -1, -1):
            if args[i] is None:
                args.pop(i)
        argsPaired = []
        for i in range(0, len(args), 2):
            argsPaired.append({"rtype": args[i], "varname": args[i+1]})
        return {
            "type": InstructionTypes.FunctionStart,
            "fname": funcname, 
            "rtype": rtype,
            "args": argsPaired
        }
    elif "=" in line and "==" not in line and "+=" not in line and "<=" not in line and ">=" not in line and "!=" not in line:
        if re.match(r"[a-zA-Z]*[0-9]+[a-zA-Z][a-zA-Z0-9]*=", line) is not None:  # variable definition
            expr = "([a-zA-Z]*[0-9]+)([a-zA-Z][a-zA-Z0-9]*)=(.*)"
            matches = re.match(expr, line).groups()
            vartype = matches[0]
            varname = matches[1]
            varcontents = parseLiteral(matches[2])
            if varcontents is None:
                varcontents = parseLine(matches[2])
            return {
                "type": InstructionTypes.VariableDef,
                "vartype": vartype,
                "name": varname,
                "contents": varcontents
            }
        else:  # variable modification
            expr = "([a-zA-Z]+)=(.*)"
            matches = re.match(expr, line).groups()
            varname = matches[0]
            return {
                "type": InstructionTypes.VariableMod,
                "name": varname,
                "contents": parseLiteral(matches[1])
            }
    
    elif "+=" in line:  # add to variable
        expr = "([a-zA-Z][a-zA-Z0-9]*)\+=(.*)"
        matches = re.match(expr, line).groups()
        return {
            "type": InstructionTypes.VariableOperatorPlusEquals,
            "name": matches[0],
            "contents": parseLiteral(matches[1])
        }

    elif "(" in line and ")" in line:  #TODO: use regex
        expr = "([a-zA-Z][a-zA-Z0-9]*)\((.*?)\)"
        matches = re.match(expr, line).groups()
        funcname = matches[0]
        arguments = matches[1].split(",")
        parsedArgs = []
        for arg in arguments:
            parsedArgs.append(parseLiteral(arg))
        
        return {
            "type": InstructionTypes.FunctionCall,
            "fname": funcname,
            "args": parsedArgs
        }
    
    elif line[0] == "}":
        return {
            "type": InstructionTypes.FunctionEnd,
            "fname": line[1:]
        }


def parseLiteral(arg):
    intExpr = "^(\d+)$"
    charExpr = "^'(.+)'$"
    varExpr = "^([a-zA-Z][a-zA-Z0-9_]*)$"
    operationExpr = r"(.+?)(\+)(.+)"
    logicalExpr = r"^(.+?)(<|<=|>|>=|==)([a-zA-Z0-9']+)$"
    functionExpr = r"([a-zA-Z][a-zA-Z0-9_]*)\((.*?)\)"
    if (result := re.match(intExpr, arg)) is not None:
        return {"type": "int", "value": result.group(1)}
    if (result := re.match(charExpr, arg)) is not None:
        c = result.group(1)
        if c == "\\n":
            return {"type": "int", "value": 0x0a}
        else:
            if len(c) > 1: raise Exception(f"[***] Not a single character")
            return {"type": "int", "value": ord(result.group(1))}
    if (result := re.match(varExpr, arg)) is not None:
        return {"type": "var", "value": result.group(1)}
    if (result := re.match(operationExpr, arg)) is not None:
        return {"type": "operation", "optype": result.group(2), "v1": parseLiteral(result.group(1)), "v2": parseLiteral(result.group(3))}
    if (result := re.match(logicalExpr, arg)) is not None:
        return {"type": "logical_op", "optype": result.group(2), "v1": parseLiteral(result.group(1)), "v2": parseLiteral(result.group(3))}
    if (result := re.match(functionExpr, arg)) is not None:  # todo: fix this
        args = ""
        for arg in result.group(2).split(","):
            pass


def increaseVarMemoryPosition(positions: dict, ignore, increaseAmount):
    for k, v in positions.items():
        if k != ignore:
            positions[k] += increaseAmount

    return positions


def if_statement(condition, jmpFunc, varMemoryPositions):
    rval = b""
    if condition["type"] != "logical_op": raise Exception("While loop should be run with logical operator")
    if condition["v1"]["type"] != "var": raise Exception("First item in while loop conditional should be variable")
    rval += b"\x48\x89\xe0"  # mov rax, rsp
    addAmount = varMemoryPositions[condition["v1"]["value"]]
    if addAmount > 0:
        rval += b"\x48\x83\xc0" + int(addAmount).to_bytes(1, byteorder="little") # add rax, {addAmount}
    rval += b"\x48\xc7\xc3" + int(condition["v2"]["value"]).to_bytes(4, byteorder="little")  # mov rbx, {value}
    rval += b"\x66\x39\x18"  # cmp word [rax], bx
    if condition["optype"] == "<":
        rval += b"\x7c"  # jl
    elif condition["optype"] == "<=":
        rval += b"\x7e"  # jle
    elif condition["optype"] == ">":
        rval += b"\x7f"  # jg
    elif condition["optype"] == ">=":
        rval += b"\x7d"  # jge
    elif condition["optype"] == "==":
        rval += b"\x74"  # je
    elif condition["optype"] == "!=":
        rval += b"\x75"  # jne
    else:
        rval += b"\xeb"  # unconditional jump if no valid condition is given 
    
    rval += jmpFunc(len(rval))
    return rval


def main():
    with open("test.tpl") as f:
        code = f.read()

    code = code.replace("\n", "").replace(" ", "")
    code = code.split(";")
    print(code)

    
    ### TOKENISE FIRST :)


    instructions = []

    for linenum, line in enumerate(code):
        linenum = linenum + 1
        instructions.append(parseLine(line))
        
    print(instructions)

    ### WRITING INTO BINARY

    textSection = b""

    varMemoryPositions = {}
    varTypes = {}
    whileBlocks = {}
    ifBlocks = {}
    functionDefBlocks = {}
    functionArgs = {}
    memPointer = 0  # in bits

    for ins in instructions:
        if ins["type"] == InstructionTypes.FunctionStart:
            if ins["fname"] == "main":
                textSection = b"\xeb" + (len(textSection)).to_bytes(1, byteorder="little") + textSection  # add jump to main function
                for block in functionDefBlocks.keys():
                    functionDefBlocks[block] += 2
            else:
                functionDefBlocks[ins["fname"]] = len(textSection)
                functionArgs[ins["fname"]] = ins["args"]

                for arg in ins["args"]:
                    varMemoryPositions[arg["varname"]] = 8
                    varMemoryPositions = increaseVarMemoryPosition(varMemoryPositions, arg["varname"], 8)
        elif ins["type"] == InstructionTypes.FunctionEnd:
            if ins["fname"] == "main":
                textSection += b"\xB8\x3C\x00\x00\x00\x48\x31\xFF\x0F\x05" # mov rax, 60 ; xor rdi, rdi ; syscall
            elif ins["fname"].startswith("while"):
                print(whileBlocks)

                condition = whileBlocks[ins["fname"]][0]
                #textSection += (0xff - len(textSection) -  int(whileBlocks[ins["fname"]][1]) + 4).to_bytes(1, byteorder="little")
                print(hex(len(textSection)), hex(int(whileBlocks[ins["fname"]][1])))
                textSection += if_statement(condition, lambda addLen: (0xff - addLen - len(textSection) + int(whileBlocks[ins["fname"]][1])).to_bytes(1, byteorder="little"), varMemoryPositions)
            elif ins["fname"].startswith("if"):
                print(ifBlocks)

                textSection = textSection[:ifBlocks[ins["fname"]][1] - 1] + (len(textSection) - ifBlocks[ins["fname"]][1]).to_bytes(1, byteorder="little") + textSection[ifBlocks[ins["fname"]][1]:]
            else:  # it is a custom function definition
                for arg in functionArgs[ins["fname"]]:
                    varMemoryPositions = increaseVarMemoryPosition(varMemoryPositions, arg["varname"], -8)

                textSection += b"\xc3"  # ret
        elif ins["type"] == InstructionTypes.FunctionCall:
            if ins["fname"] == "putc":
                if len(ins["args"]) > 1: raise Exception(f"[{linenum}] Too many arguments for builtin function `putc`")
                if ins["args"][0]["type"] == "int":
                    textSection += b"\x6a" + int(ins["args"][0]["value"]).to_bytes(1, byteorder="little") # push
                textSection += b"\xB8\x01\x00\x00\x00"  # mov rax, 1
                textSection += b"\xBF\x01\x00\x00\x00"  # mov rdi, 1
                textSection += b"\xBA\x01\x00\x00\x00"  # mov rdx, 1 ;
                textSection += b"\x48\x89\xE6"  # mov rsi, rsp
                if ins["args"][0]["type"] == "var":
                    addAmount = varMemoryPositions[ins["args"][0]["value"]]
                    if addAmount > 0:
                        textSection += b"\x48\x83\xc6" + int(addAmount).to_bytes(1, byteorder="little") # add rsi, {addAmount}
                textSection += b"\x0F\x05"  # syscall
                if ins["args"][0]["type"] == "int":
                    textSection += b"\x58"  # pop rax
            elif ins["fname"] == "mod":
                if ins["args"][0]["type"] == "int":
                    textSection += b"\x48\xc7\xc0" + int(ins["args"][0]["value"]).to_bytes(4, byteorder="little") # mov rax, {val}
                elif ins["args"][0]["type"] == "var":
                    textSection += b"\x48\x89\xE6"  # mov rsi, rsp
                    addAmount = varMemoryPositions[ins["args"][0]["value"]]
                    if addAmount > 0:
                        textSection += b"\x48\x83\xc6" + int(addAmount).to_bytes(1, byteorder="little") # add rsi, {addAmount}
                        textSection += b"\x48\x8b\x06"  # mov rax, [rsi]
                
                if ins["args"][1]["type"] == "int":
                    textSection += b"\x48\xc7\xc3" + int(ins["args"][0]["value"]).to_bytes(4, byteorder="little") # mov rax, {val}
                elif ins["args"][1]["type"] == "var":
                    textSection += b"\x48\x89\xE6"  # mov rsi, rsp
                    addAmount = varMemoryPositions[ins["args"][1]["value"]]
                    if addAmount > 0:
                        textSection += b"\x48\x83\xc6" + int(addAmount).to_bytes(1, byteorder="little") # add rsi, {addAmount}
                        textSection += b"\x48\x8b\x1e"  # mov rbx, [rsi]
            elif ins["fname"].startswith("while"):
                whileBlocks[ins["fname"]] = (ins["args"][0], len(textSection))  # condition for loop continuation and where to jump to
            elif ins["fname"].startswith("if"):
                # Jump if condition is NOT true (swap condition to opposite and jump if true)
                if ins["args"][0]["optype"] == "==":
                    ins["args"][0]["optype"] = "!="
                textSection += if_statement(ins["args"][0], lambda addLen: addLen.to_bytes(1, byteorder="little"), varMemoryPositions)
                ifBlocks[ins["fname"]] = (ins["args"][0], len(textSection))
            else:  # custom function call
                for i, arg in enumerate(ins["args"]):
                    textSection += b"\x6a" + int(arg["value"]).to_bytes(1, byteorder="little")  # push
                    # create variable
                textSection += b"\xe8" + (0xffffffff - len(textSection) - functionDefBlocks[ins["fname"]]).to_bytes(4, byteorder="little")  # call {func}
                for arg in ins["args"]:
                    textSection += b"\x58"  # pop
        elif ins["type"] == InstructionTypes.VariableDef:
            if ins["vartype"] == "i8":
                varTypes[ins["name"]] = ins["vartype"]
                textSection += b"\x6a" + int(ins["contents"]["value"]).to_bytes(1, byteorder="little") # push
                varMemoryPositions[ins["name"]] = 0
                varMemoryPositions = increaseVarMemoryPosition(varMemoryPositions, ins["name"], 8)
                memPointer += 8
        elif ins["type"] == InstructionTypes.VariableMod:
            if varTypes[ins["name"]] == "i8":
                if ins["contents"]["type"] == "int":
                    textSection += b"\x48\x89\xe0"  # mov rax, rsp
                    addAmount = varMemoryPositions[ins["name"]]
                    if addAmount > 0:
                        textSection += b"\x48\x83\xc0" + int(addAmount).to_bytes(1, byteorder="little") # add rax, {addAmount}
                    textSection += b"\x66\xc7\x00" + int(ins["contents"]["value"]).to_bytes(2, byteorder="little")  # mov word [rax], {val}
        elif ins["type"] == InstructionTypes.VariableOperatorPlusEquals:
            if varTypes[ins["name"]] == "i8":
                if ins["contents"]["type"] == "int":
                    textSection += b"\x48\x89\xe0"  # mov rax, rsp
                    addAmount = varMemoryPositions[ins["name"]]
                    if addAmount > 0:
                        textSection += b"\x48\x83\xc0" + int(addAmount).to_bytes(1, byteorder="little") # add rax, {addAmount}
                    textSection += b"\x66\x83\x00" + int(ins["contents"]["value"]).to_bytes(1, byteorder="little")  # mov word [rax], {val}

    print(varMemoryPositions)
    headerSection = b""

    ## FILE HEADER

    headerSection += b"\x7fELF"  # magic number
    headerSection += b"\x02"  # 64-bit mode
    headerSection += b"\x01"  # little endian
    headerSection += b"\x01"  # v1 of elf
    headerSection += b"\x00"  # system v (basic linux)
    headerSection += b"\x00"  # os version
    headerSection += b"\0\0\0\0\0\0\0"  # padding (7 bytes)
    headerSection += b"\x02\x00"  # file type = executable file
    headerSection += b"\x3e\x00"  # machine type = AMD x86-64
    headerSection += b"\x01\x00\x00\x00"  # v1 of elf
    headerSection += b"\x80\x00\x40\x00\0\0\0\0"  # memory entry point
    headerSection += b"\x40\0\0\0\0\0\0\0"  # start of header table (end of this header)
    headerSection += b"\x98\x01\0\0\0\0\0\0"  # start of section header table #TODO: move this somewhere smart
    headerSection += b"\0\0\0\0"  # flags
    headerSection += b"\x40\x00"  # header size (64 bytes)
    headerSection += b"\x38\x00"  # size of program header table entry
    headerSection += b"\x01\x00"  # number of program headers in table
    headerSection += b"\x40\x00"  # size of section header table entry
    headerSection += b"\x05\x00"  # number of section headers in table
    headerSection += b"\x04\x00"  # index of section header table with section names

    ## PROGRAM HEADER (starts at 0x40)

    headerSection += b"\x01\x00\x00\x00"  # type of segment = loadable segment
    headerSection += b"\x05\x00\x00\x00"  # flags i dont understand
    headerSection += b"\0\0\0\0\0\0\0\0"  # offset of segment in file image
    headerSection += b"\0\0\x40\x00\0\0\0\0"  # virtual address of segment in memory
    headerSection += b"\0\0\x40\x00\0\0\0\0"  # segment's physical address
    headerSection += (0x80 + len(textSection)).to_bytes(8, byteorder="little")  # size of segment in file
    headerSection += (0x80 + len(textSection)).to_bytes(8, byteorder="little")  # size of segment in memory
    headerSection += b"\x00\x00\x20\x00\0\0\0\0"  # alignment
    headerSection += b"\0\0\0\0\0\0\0\0"  # idk what this padding is for, probably alignment or smth


    # TODO: sections


    with open("compiled", "wb") as f:
        f.write(headerSection + textSection)


    #print(binascii.hexlify(bytearray(textSection)))


if __name__ == "__main__":
    main()