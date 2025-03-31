中文说明[看这里](https://github.com/Cofflag/csm3sc/wiki)

# CSM3SC

This is a simple script disassembler and assembler for Summon Night Swordcraft Story 3: Stone of Beginnings (サモンナイト クラフトソード物語 はじまりの石), aka csm3.

## Usage

`disasm.py <in.bin> <opcodes.yaml> <tbl.txt> <out.txt>`
where `in.bin` is the script binary to disassemble, and `out.txt` is the result.

`asm.py <in.txt> <opcodes.yaml> <tbl.txt> <out.bin>`
where `in.txt` is the script text to assemble, and `out.bin` is the result.

`opcodes.yaml` and `tbl.txt` are provided in the repo, and they need improvment.

`unlzsc974.bin` ,`974.bin` and `974.txt` are provided as examples.

## op.yaml

This is the definition of the csm3 script's opcode.

`unkxxxx` needs documentation.

If you find out the usage of any unknown opcode, please add it to the yaml file and send a pull request. Thank you.

## tbl.txt

This is the char table of csm3's Chinese version.

If you are using the Japanese version, replace it with shift-jis char table.

The table isn't complete, because I haven't reversed the glyph drawing functions of the game. This table is modified from sjis.

If you find out wrong chars or you can provide a better table, please sent a pull request.

## in.bin

This is the binary script extract from the rom.

You can use the python script below to get rom offsets of them:

```
baseAddr = 0x09718ffc
fileName = 'base3.gba'
arraySize = 0xc00
with open(fileName, "rb") as f:
	offs = baseAddr - 0x08000000
	f.seek(offs)
	i = 0x0
	while i < arraySize:
		f.seek(offs + i * 8 + 8)
		lzof = f.read(4)
		i = i + 1
		print(hex(int.from_bytes(lzof, byteorder='little', signed = False) * 16 + offs))
```

Once you have the offsets, you can use a lzss decompressor to decompress the script.

### Why don't you provide the decompressor?

I want to keep this repo mainly focused on disassemble and assemble. You can find tools like [dkcomp](https://github.com/Kingizor/dkcomp) or CT2 to decompress the scripts, or you can make tools by yourself. You can find the decompress algorithm on GBATEK. 

## Requirements

This tool requires pyyaml. You can `pip install pyyaml` to install it.
