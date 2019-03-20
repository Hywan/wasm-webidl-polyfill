#!/usr/bin/env python

import json
import os
import sys

def leb_u32(value):
  assert value >= 0, "Unsigned LEBs must have signed value"
  leb = []
  while True:
    byte = value & 0x7f
    value >>= 7
    if value == 0:
      leb.append(byte)
      break
    else:
      leb.append(byte | 0x80)
  return leb

def binary_u32(value):
  binary = []
  for i in xrange(4):
    byte = value & 0xff
    value >>= 8
    binary.append(byte)
  return binary

def custom_section_binary(section_name, data):
  binary_size = (
    len(data) +
    len(section_name) +
    1
  )

  # iterate until size_leb reaches a fixed point (should be very fast)
  size_leb = leb_u32(binary_size)
  last_size = 1
  while len(size_leb) != last_size:
    binary_size += len(size_leb) - last_size
    last_size = len(size_leb)
    size_leb = leb_u32(binary_size)

  return (
    [0] + # custom section
    size_leb + # payload_len
    str_encode(section_name) +
    data
  )

def parse_sexprs(text):
  stack = [[]]
  cur = ''
  def sep():
    if cur != '':
      stack[-1].append(cur)
    return ''
  for i in xrange(len(text)):
    c = text[i]
    if c == '(':
      cur = sep()
      stack.append([])
    elif c == ')':
      cur = sep()
      top = stack[-1]
      stack = stack[0:-1]
      stack[-1].append(top)
    elif c.isspace():
      cur = sep()
    else:
      cur += c
  return stack[0]

WEBIDL_TYPES = {
  'DOMString': 0,
}

def str_encode(text):
  return leb_u32(len(text)) + [ord(c) for c in text]

def parse_webidl(contents):
  def flatten(lst):
    return [item for sublist in lst for item in sublist]
  def segment(part):
    return leb_u32(len(part)) + flatten(part)
  def outgoingBytes(sexpr):
    head = sexpr[0]
    if head == 'utf8-cstr':
      assert sexpr[1][0] == 'type'
      assert sexpr[2][0] == 'off-idx'
      idByte = 0
      ty = WEBIDL_TYPES[sexpr[1][1]]
      off = int(sexpr[2][1])
      return [idByte, ty, off]
  def inExpr(sexpr):
    head = sexpr[0]
    if head == 'get':
      idByte = 0
      off = int(sexpr[1])
      return [idByte, off]
  def incomingBytes(sexpr):
    head = sexpr[0]
    if head == 'alloc-utf8-cstr':
      assert sexpr[1][0] == 'alloc-export'
      idByte = 0
      name = sexpr[1][1][1:-1]
      expr = inExpr(sexpr[2])
      return [idByte] + str_encode(name) + expr
  idl_section = contents.split('(;webidl')[1].split('webidl;)')[0].strip()
  sexprs = parse_sexprs(idl_section)
  data = []
  for elem in sexprs:
    assert elem[0] == 'webidl-func-binding'
    if elem[1] == 'import':
      namespace = elem[2][1:-1]
      name = elem[3][1:-1]

      params = []
      results = []
      for x in elem[4:]:
        if x[0] == "param":
          for param in x[1:]:
            params.append(outgoingBytes(param))
        else:
          assert x[0] == "result"
          for result in x[1:]:
            results.append(incomingBytes(result))
      import_byte = 0
      data.append([import_byte] +
        str_encode(namespace) +
        str_encode(name) +
        segment(params) +
        segment(results)
      )
    else:
      assert elem[1] == "export"

  return segment(data)

def main(args):
  assert len(args) == 2, "Must have infile and outfile (in that order)"
  infile = args[0]
  outfile = args[1]
  contents = open(infile, 'r').read()
  data = parse_webidl(contents)
  binary = custom_section_binary('webIDLBindings', data)
  with open(outfile, 'wb') as f:
    for byte in binary:
      f.write(chr(byte))
  return 0

if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
