def without_comments(text):
    output = []
    depth = 0
    for line in text.splitlines():
        code = []
        i = 0
        quoted = False
        while i < len(line):
            if depth:
                if line.startswith("/*", i):
                    depth += 1
                    i += 2
                elif line.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            elif quoted:
                code.append('"' if line[i] == '"' else " ")
                if line[i] == "\\":
                    i += 2
                elif line[i] == '"':
                    quoted = False
                    i += 1
                else:
                    i += 1
            elif line.startswith("//", i):
                break
            elif line.startswith("/*", i):
                depth += 1
                i += 2
            else:
                quoted = line[i] == '"'
                code.append(line[i])
                i += 1
        output.append("".join(code))
    return "\n".join(output)

def rust_lines(text):
    return sum(bool(line.strip()) for line in without_comments(text).splitlines())

