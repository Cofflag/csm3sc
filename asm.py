import sys
import yaml
import struct
import re
from collections import deque

class Assembler:
    def __init__(self, yaml_path, tbl_path):
        with open(yaml_path) as f:
            self.opcodes = yaml.safe_load(f)['opcodes']
            self.name_to_opcode = {
                v['name']: (int(k, 16), v['parameters']) 
                for k, v in self.opcodes.items()
            }

        self.operators = {
            '==': 0x8B, '!=': 0x8C, '<': 0x87, '<=': 0x88,
            '>': 0x89, '>=': 0x8A, '+': 0x85, '-': 0x86,
            '*': 0x82, '/': 0x83, '%': 0x84, '!': 0x80,
            '~': 0x81, '&': 0x8D, '^': 0x8E, '|': 0x8F, 
            '||': 0x90, '&&': 0x91
        }
        self.tbl = {}
        with open(tbl_path) as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    code_part, char_part = line.split('=', 1)
                    if code_part == '8140':
                        continue
                    self.tbl[char_part.strip()] = int(code_part.strip(), 16)
                    self.tbl[' '] = 0x8140

        self.labels = {}
        self.patches = []
    
    def _parse_expression(self, expr):
        operators = {
            '==': 0x8B, '!=': 0x8C, '<': 0x87, '<=': 0x88,
            '>': 0x89, '>=': 0x8A, '+': 0x85, '-': 0x86,
            '*': 0x82, '/': 0x83, '%': 0x84, '!': 0x80,
            '~': 0x81, '&': 0x8D, '^': 0x8E, '|': 0x8F, 
            '||': 0x90, '&&': 0x91
        }

        pattern = r'''
            (@?0x[\dA-Fa-f]+) |    # 十六进制数或标签
            (\d+) |                # 十进制数
            (\(s16\)) |            # 类型转换
            (\(s8\)) |
            (gUnk_\w+\[\d+\]) |    # 变量访问
            (&&|\|\||==|!=|<=|>=|<|>|\+|\-|\*|/|%|!|~|&|\^|\|) | # 操作符
            (\(|\))                # 括号
        '''
        tokens = re.findall(pattern, expr, re.VERBOSE)
        tokens = [max(t, key=bool) for t in tokens if any(t)]
    
        output = []
        stack = []
        for token in tokens:
            if token in operators:
                while stack and stack[-1] != '(' and \
                        self._get_precedence(stack[-1]) >= self._get_precedence(token):
                    output.append(stack.pop())
                stack.append(token)
            elif token == '(':
                stack.append(token)
            elif token == ')':
                while stack[-1] != '(':
                    output.append(stack.pop())
                stack.pop()
            else:
                output.append(token)
    
        while stack:
            output.append(stack.pop())
    
        return output
    
    def _compile_expression(self, rpn):
        binary = bytearray()
        var_pattern = re.compile(r'gUnk_(\w+)\[(\d+)\]')
    
        for token in rpn:
            if token in ('(s16)', '(s8)'):
                continue

            if var_match := var_pattern.match(token):
                var_name, offset = var_match.groups()
                offset = int(offset)

                if var_name in ['030067B0', '03006584', '0300657C']:
                    binary += struct.pack('<H', 0x0002)
                    if var_name == '030067B0':
                        binary += struct.pack('<H', offset)
                    elif var_name == '03006584':
                        binary += struct.pack('<H', offset + 0x180)
                    else:
                        binary += struct.pack('<H', offset + 0x80)
                else:
                    binary += struct.pack('<H', 0x0003)
                    if var_name == '030067AC':
                        binary += struct.pack('<H', offset)
                    elif var_name == '030067A8':
                        binary += struct.pack('<H', offset + 0x100)
                    else:
                        binary += struct.pack('<H', offset + 0x20)
                    
            # 处理操作符
            elif token in self.operators:
                binary += struct.pack('<H', self.operators[token])
                
            # 处理立即数
            elif token.startswith('0x') or token.isdigit():
                value = int(token, 0)
                binary += struct.pack('<H', 0x0001)
                binary += struct.pack('<H', value)
                
            else:
                raise ValueError(f"Unrecognized token: {token}")
    
        binary += struct.pack('<H', 0x0000)
        return binary
    
    def _get_precedence(self, op):
        return {
            '!':4, '~':4, 
            '*':3, '/':3, '%':3,
            '+':2, '-':2,
            '<':1, '>':1, '<=':1, '>=':1,
            '==':1, '!=':1,
            '&':0, '^':0, '|':0, '&&':0, '||':0
        }.get(op, 0)

    def _encode_string(self, s):
        s = s.strip("'")
        binary = bytearray()
        for c in s:
            code = self.tbl.get(c, 0xFFFD)  # 替换字符为0xFFFD如果未找到
            binary += struct.pack('>H', code)
        binary += b'\x00\x00'
        return binary
    
    def _split_parameters(self, param_str):
        params = []
        current = []
        in_quote = False
        for c in param_str:
            if c == "'":
                in_quote = not in_quote
                current.append(c)
            elif not in_quote and c == ',':
                param = ''.join(current).strip()
                if param:
                    params.append(param)
                current = []
            else:
                current.append(c)
        
        param = ''.join(current).strip()
        if param:
            params.append(param)
        
        return params

    def assemble(self, asm_path, out_path):
        self.labels = {}
        self.patches = []
        binary = bytearray()
        
        with open(asm_path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith(';'):
                    continue

                labels = []
                remaining_line = line
                while True:
                    if remaining_line.startswith('@'):
                        colon_pos = remaining_line.find(':')
                        if colon_pos == -1:
                            break
                        label_name = remaining_line[1:colon_pos].strip()
                        labels.append(label_name)
                        remaining_line = remaining_line[colon_pos+1:].strip()
                    else:
                        break

                for label in labels:
                    if label in self.labels:
                        raise ValueError(f"Line {line_num}: Duplicate label '@{label}'")
                    self.labels[label] = len(binary)

                if not remaining_line:
                    continue
                
                # 分割操作码和参数
                parts = remaining_line.split(None, 1)
                opname = parts[0]
                param_str = parts[1] if len(parts) > 1 else ""
                
                if opname not in self.name_to_opcode:
                    raise ValueError(f"Line {line_num}: Unknown opcode '{opname}'")
                
                opcode, params_def = self.name_to_opcode[opname]
                binary += struct.pack('<H', opcode)

                params = self._split_parameters(param_str)

                if len(params) != len(params_def):
                    raise ValueError(
                        f"Line {line_num}: Expected {len(params_def)} parameters for {opname}, "
                        f"got {len(params)}. Full line: {line}"
                    )

                for i, (p_def, p_val_raw) in enumerate(zip(params_def, params)):
                    p_type = p_def['type']
                    p_val = p_val_raw.strip()
                    
                    try:
                        if p_type == 'imm16':
                            value = int(p_val, 0)
                            binary += struct.pack('<H', value)
                        
                        elif p_type == 'label':
                            if not p_val.startswith('@'):
                                raise ValueError(f"Label must start with @, got '{p_val}'")
                            label_name = p_val[1:]
                            # 写入临时0并记录修补位置
                            binary += struct.pack('<H', 0)
                            patch_pos = len(binary) - 2
                            self.patches.append( (patch_pos, label_name) )
                        
                        elif p_type == 'str':
                            if not (p_val.startswith("'") and p_val.endswith("'")):
                                raise ValueError(f"String must be quoted, got '{p_val}'")
                            binary += self._encode_string(p_val)
                        
                        elif p_type == 'expr':
                            rpn = self._parse_expression(p_val)
                            expr_binary = self._compile_expression(rpn)
                            binary += expr_binary
                        
                        else:
                            raise ValueError(f"Unsupported parameter type: {p_type}")
                    
                    except Exception as e:
                        raise ValueError(
                            f"Line {line_num} parameter {i+1} ({p_type}) error: {str(e)}\n"
                            f"Full parameter: '{p_val_raw}'\n"
                            f"Full line: {line}"
                        ) from e

        for pos, label_name in self.patches:
            if label_name not in self.labels:
                raise ValueError(f"Undefined label '@{label_name}'")
            address = self.labels[label_name]
            binary[pos:pos+2] = struct.pack('<H', address)

        header = bytearray(b'PSI3') 
        file_size = len(binary) + 0x10
        header += struct.pack('<H', file_size)
        header += bytes(0x10 - len(header))

        final_binary = header + binary

        with open(out_path, 'wb') as f:
            f.write(final_binary)

if __name__ == '__main__':
    if len(sys.argv) != 5:
        print("Usage: asm.py <in.txt> <opcodes.yaml> <tbl.txt> <out.bin>")
        sys.exit(1)
    
    assembler = Assembler(sys.argv[2], sys.argv[3])
    try:
        assembler.assemble(sys.argv[1], sys.argv[4])
    except Exception as e:
        print(f"Assembly error: {str(e)}")
        sys.exit(2)
