import sys
import yaml
import struct
from collections import deque

class Disassembler:
    def __init__(self, yaml_path, tbl_path):
        with open(yaml_path) as f:
            self.opcodes = yaml.safe_load(f)['opcodes']
        self.tbl = {}
        with open(tbl_path) as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    code, char = line.split('=', 1)
                    if code == '8140':
                        continue
                    self.tbl[int(code, 16)] = char.strip()
        self.tbl[0x8140] = ' '
        self.expr_stack = deque()
        self.called_labels = set()

    def _read_u16(self, data, offset):
        return struct.unpack('<H', data[offset:offset+2])[0]

    def _read_u16_big(self, data, offset):
        return struct.unpack('>H', data[offset:offset+2])[0]

    def _parse_imm16(self, data, offset):
        value = self._read_u16(data, offset)
        return offset + 2, str(value)

    def _parse_label(self, data, offset):
        value = self._read_u16(data, offset)
        return offset + 2, f"@label_{value}"

    def _parse_str(self, data, offset):
        chars = []
        while True:
            code = self._read_u16_big(data, offset)
            offset += 2
            if code == 0:
                break
            chars.append(self.tbl.get(code, "啊"))
        return offset, "'" + "".join(chars) + "'"

    def _parse_expr(self, data, offset):
        start_offset = offset
        self.expr_stack = []
        operators = {
            0x80: ('!', 1),
            0x81: ('~', 1),
            0x82: ('*', 2),
            0x83: ('/', 2),
            0x84: ('%', 2),
            0x85: ('+', 2),
            0x86: ('-', 2),
            0x87: ('<', 2),
            0x88: ('<=', 2),
            0x89: ('>', 2),
            0x8A: ('>=', 2),
            0x8B: ('==', 2),
            0x8C: ('!=', 2),
            0x8D: ('&', 2),
            0x8E: ('^', 2),
            0x8F: ('|', 2),
            0x90: ('||', 2),
            0x91: ('&&', 2),
        }
        precedence = {
            '!': 4, '~': 4,
            '*': 3, '/': 3, '%': 3,
            '+': 2, '-': 2,
            '<': 1, '<=': 1, '>': 1, '>=': 1,
            '==': 1, '!=': 1,
            '&': 0, '^': 0, '|': 0, '||': 0, '&&': 0
        }
        while offset < len(data):
            opcode = self._read_u16(data, offset)
            offset += 2
            if opcode == 0x0000:
                break
            if opcode == 0x0001:
                imm = self._read_u16(data, offset)
                offset += 2
                self.expr_stack.append({'val': str(imm), 'prec': 999})
            elif opcode == 0x0002:
                var_op = self._read_u16(data, offset)
                offset += 2
                if var_op <= 0x3F:
                    self.expr_stack.append({'val': f'gUnk_030067B0[{var_op}]', 'prec': 999})
                elif var_op > 0x17F:
                    self.expr_stack.append({'val': f'(s8)gUnk_03006584[{var_op-0x180}]', 'prec': 999})
                else:
                    self.expr_stack.append({'val': f'(s16)gUnk_0300657C[{var_op-0x80}]', 'prec': 999})
            elif opcode == 0x0003:
                var_op = self._read_u16(data, offset)
                offset += 2
                if var_op <= 0x1F:
                    self.expr_stack.append({'val': f'gUnk_030067AC[{var_op}]', 'prec': 999})
                elif var_op > 0xFF:
                    self.expr_stack.append({'val': f'(s8)gUnk_030067A8[{var_op-0x100}]', 'prec': 999})
                else:
                    self.expr_stack.append({'val': f'(s8)gUnk_03006570[{var_op-0x20}]', 'prec': 999})
            elif opcode in operators:
                op, argc = operators[opcode]
                if len(self.expr_stack) < argc:
                    break
                if argc == 1:
                    a = self.expr_stack.pop()
                    expr = f"{op}({a['val']})" if a['prec'] < precedence[op] else f"{op}{a['val']}"
                    self.expr_stack.append({'val': expr, 'prec': precedence[op]})
                else:
                    b = self.expr_stack.pop()
                    a = self.expr_stack.pop()
                    a_str = a['val'] if a['prec'] >= precedence[op] else f"({a['val']})"
                    b_str = b['val'] if b['prec'] >= precedence[op] else f"({b['val']})"
                    expr = f"{a_str} {op} {b_str}"
                    self.expr_stack.append({'val': expr, 'prec': precedence[op]})
            else:
                offset -= 2
                break
        expr = " ".join([item['val'] for item in self.expr_stack]) if self.expr_stack else "???"
        return offset, expr

    def disassemble(self, bin_path, out_path):
        with open(bin_path, 'rb') as f:
            data = f.read()[0x10:]

        self.called_labels.clear()
        pre_offset = 0
        while pre_offset < len(data):
            if pre_offset + 2 > len(data):
                break
            opcode = self._read_u16(data, pre_offset)
            pre_offset += 2
            hex_opcode = f"0x{opcode:04X}"
            op_def = self.opcodes.get(hex_opcode, {'parameters': []})
            for param in op_def.get('parameters', []):
                p_type = param.get('type', 'unknown')
                if p_type == 'label':
                    if pre_offset + 2 > len(data):
                        break
                    label_value = self._read_u16(data, pre_offset)
                    self.called_labels.add(label_value)
                    pre_offset += 2
                elif p_type == 'imm16':
                    pre_offset += 2
                elif p_type == 'str':
                    while pre_offset + 2 <= len(data):
                        code = self._read_u16_big(data, pre_offset)
                        pre_offset += 2
                        if code == 0:
                            break
                elif p_type == 'expr':
                    new_offset, _ = self._parse_expr(data, pre_offset)
                    pre_offset = new_offset
                else:
                    pass

        output = []
        offset = 0
        while offset < len(data):
            if offset in self.called_labels:
                output.append('\n')
                output.append(f'@label_{offset}:')
            if offset + 2 > len(data):
                break
            opcode = self._read_u16(data, offset)
            current_op_offset = offset
            offset += 2
            hex_opcode = f"0x{opcode:04X}"
            op_def = self.opcodes.get(hex_opcode, {'name': f'unk{opcode:04X}', 'parameters': []})
            params = []
            for param in op_def.get('parameters', []):
                p_type = param.get('type', 'unknown')
                if p_type == 'imm16':
                    offset, val = self._parse_imm16(data, offset)
                elif p_type == 'label':
                    offset, val = self._parse_label(data, offset)
                elif p_type == 'str':
                    offset, val = self._parse_str(data, offset)
                elif p_type == 'expr':
                    offset, val = self._parse_expr(data, offset)
                else:
                    val = '?'
                params.append(val)
            line = f"{op_def['name']} {', '.join(params)}"
            output.append(line)

        with open(out_path, 'w') as f:
            f.write('\n'.join(output))

if __name__ == '__main__':
    if len(sys.argv) != 5:
        print("Usage: disasm.py <in.bin> <opcodes.yaml> <tbl.txt> <out.txt>")
        sys.exit(1)
    disasm = Disassembler(sys.argv[2], sys.argv[3])
    disasm.disassemble(sys.argv[1], sys.argv[4])
