#-------------------------------------------------------------------------------
#   Read output of gen_json.py and generate Zig language bindings.
#
#   Zig coding style:
#   - types are PascalCase
#   - functions are camelCase
#   - otherwise snake_case
#-------------------------------------------------------------------------------
import json
import re

struct_types = []
c_struct_types = []     # structs that have a C compatible memory layout
enum_types = []
enum_items = {}

re_1d_array = re.compile("^(?:const )?\w*\s\*?\[\d*\]$")
re_2d_array = re.compile("^(?:const )?\w*\s\*?\[\d*\]\[\d*\]$")

prim_types = {
    'int':      'i32',
    'bool':     'bool',
    'int8_t':   'i8',
    'uint8_t':  'u8',
    'int16_t':  'i16',
    'uint16_t': 'u16',
    'int32_t':  'i32',
    'uint32_t': 'u32',
    'int64_t':  'i64',
    'uint64_t': 'u64',
    'float':    'f32',
    'double':   'f64'
}

prim_defaults = {
    'int':      '0',
    'bool':     'false',
    'int8_t':   '0',
    'uint8_t':  '0',
    'int16_t':  '0',
    'uint16_t': '0',
    'int32_t':  '0',
    'uint32_t': '0',
    'int64_t':  '0',
    'uint64_t': '0',
    'float':    '0.0',
    'double':   '0.0'
}

out_lines = ''
def l(s):
    global out_lines
    out_lines += s + '\n'

# PREFIX_BLA_BLUB to bla_blub
def as_const_name(s, prefix):
    outp = s.lower()
    if outp.startswith(prefix):
        outp = outp[len(prefix):]
    return outp

def as_zig_prim_type(s):
    return prim_types[s]

# prefix_bla_blub => BlaBlub
def as_zig_type(s):
    parts = s.lower().split('_')[1:]
    outp = ''
    for part in parts:
        outp += part.capitalize()
    return outp

# PREFIX_ENUM_BLA => Bla, _PREFIX_ENUM_BLA => Bla
def as_enum_item_name(s):
    outp = s
    if outp.startswith('_'):
        outp = outp[1:]
    parts = outp.split('_')[2:]
    outp = '_'.join(parts)
    if outp[0].isdigit():
        outp = '_' + outp
    return outp

def enum_default_item(enum_name):
    return enum_items[enum_name][0]

def is_prim_type(s):
    return s in prim_types

def is_struct_type(s):
    return s in struct_types

def is_enum_type(s):
    return s in enum_types

def is_string_ptr(s):
    return s == "const char *"

def is_const_void_ptr(s):
    return s == "const void *"

def is_void_ptr(s):
    return s == "void *"

def is_prim_ptr(s):
    for prim_type in prim_types:
        if s == f"const {prim_type} *":
            return True
    return False

def is_struct_ptr(s):
    for struct_type in struct_types:
        if s == f"const {struct_type} *":
            return True
    return False

def is_func_ptr(s):
    return '(*)' in s

def is_1d_array_type(s):
    return re_1d_array.match(s)

def is_2d_array_type(s):
    return re_2d_array.match(s)

def type_default_value(s):
    return prim_defaults[s]

def extract_array_type(s):
    return s[:s.index('[')].strip()

def extract_array_nums(s):
    return s[s.index('['):].replace('[', ' ').replace(']', ' ').split()

def extract_ptr_type(s):
    tokens = s.split()
    if tokens[0] == 'const':
        return tokens[1]
    else:
        return tokens[0]

def as_extern_c_type(arg_type):
    if arg_type == "void":
        return "void"
    elif is_prim_type(arg_type):
        return as_zig_prim_type(arg_type)
    elif is_struct_type(arg_type):
        return as_zig_type(arg_type)
    elif is_enum_type(arg_type):
        return as_zig_type(arg_type)
    elif is_void_ptr(arg_type):
        return "?*c_void"
    elif is_const_void_ptr(arg_type):
        return "?*const c_void"
    elif is_string_ptr(arg_type):
        return "[*c]const u8"
    elif is_struct_ptr(arg_type):
        return f"[*c]const {as_zig_type(extract_ptr_type(arg_type))}"
    else:
        return '???'

# get C-style arguments of a function pointer as string
def funcptr_args_c(field_type):
    tokens = field_type[field_type.index('(*)')+4:-1].split(',')
    s = ""
    for token in tokens:
        arg_type = token.strip();
        if s != "":
            s += ", "
        c_arg = as_extern_c_type(arg_type)
        if (c_arg == "void"):
            return ""
        else:
            s += c_arg
    return s

# get C-style result of a function pointer as string
def funcptr_res_c(field_type):
    res_type = field_type[:field_type.index('(*)')].strip()
    if res_type == 'void':
        return 'void'
    elif is_const_void_ptr(res_type):
        return '?*const c_void'
    else:
        return '???'

def funcdecl_args_c(decl):
    s = ""
    for param_decl in decl['params']:
        if s != "":
            s += ", "
        arg_type = param_decl['type']
        s += as_extern_c_type(arg_type)
    return s

def funcdecl_res_c(decl):
    decl_type = decl['type']
    res_type = decl_type[:decl_type.index('(')].strip()
    return as_extern_c_type(res_type)

# test if a struct has a C compatible memory layout
def struct_is_c_compatible(decl):
    c_comp = True;
    for field in decl['fields']:
        field_type = field['type']
        if is_struct_type(field_type):
            if field_type not in c_struct_types:
                c_comp = False
        # FIXME
    print(f"{decl['name']} C compatible: {c_comp}")
    return c_comp

def gen_struct(decl, prefix):
    zig_type = as_zig_type(decl['name'])
    if decl['name'] in c_struct_types:
        l(f"pub const {zig_type} = extern struct {{")
    else:
        l(f"pub const {zig_type} = struct {{")
    l(f"    pub fn init(options: anytype) {zig_type} {{ var item: {zig_type} = .{{ }}; init_with(&item, options); return item; }}")
    for field in decl['fields']:
        field_name = field['name']
        field_type = field['type']
        if is_prim_type(field_type):
            l(f"    {field_name}: {as_zig_prim_type(field_type)} = {type_default_value(field_type)},")
        elif is_struct_type(field_type):
            l(f"    {field_name}: {as_zig_type(field_type)} = .{{ }},")
        elif is_enum_type(field_type):
            l(f"    {field_name}: {as_zig_type(field_type)} = .{enum_default_item(field_type)},")
        elif is_string_ptr(field_type):
            l(f"    {field_name}: [*c]const u8 = null,")
        elif is_const_void_ptr(field_type):
            l(f"    {field_name}: ?*const c_void = null,")
        elif is_void_ptr(field_type):
            l(f"    {field_name}: ?*c_void = null,")
        elif is_prim_ptr(field_type):
            l(f"    {field_name}: ?[*]const {as_zig_prim_type(extract_ptr_type(field_type))} = null,")
        elif is_func_ptr(field_type):
            l(f"    {field_name}: ?fn({funcptr_args_c(field_type)}) callconv(.C) {funcptr_res_c(field_type)},")
        elif is_1d_array_type(field_type):
            array_type = extract_array_type(field_type)
            array_nums = extract_array_nums(field_type)
            if is_prim_type(array_type):
                zig_type = as_zig_prim_type(array_type)
                t0 = f"[{array_nums[0]}]{zig_type}"
                t1 = f"[_]{zig_type}"
                def_val = type_default_value(array_type)
                l(f"    {field_name}: {t0} = {t1}{{{def_val}}} ** {array_nums[0]},")
            elif is_struct_type(array_type):
                zig_type = as_zig_type(array_type)
                t0 = f"[{array_nums[0]}]{zig_type}"
                t1 = f"[_]{zig_type}"
                l(f"    {field_name}: {t0} = {t1}{{ .{{ }} }} ** {array_nums[0]},")
            elif is_const_void_ptr(array_type):
                l(f"    {field_name}: [{array_nums[0]}]?*const c_void = [_]?*const c_void {{ null }} ** {array_nums[0]},")
            else:
                l(f"//    FIXME: ??? array {field_name}: {field_type} => {array_type} [{array_nums[0]}]")
        elif is_2d_array_type(field_type):
            array_type = extract_array_type(field_type)
            array_nums = extract_array_nums(field_type)
            if is_prim_type(array_type):
                l(f"// FIXME: 2D array with primitive type: {field_name}")
            elif is_struct_type(array_type):
                zig_type = as_zig_type(array_type)
                t0 = f"[{array_nums[0]}][{array_nums[1]}]{zig_type}"
                l(f"    {field_name}: {t0} = [_][{array_nums[1]}]{zig_type}{{[_]{zig_type}{{ .{{ }} }}**{array_nums[1]}}}**{array_nums[0]},")
        else:
            l(f"//  {field_name}: {field_type};")
    l("};")

def gen_consts(decl, prefix):
    for item in decl['items']:
        l(f"pub const {as_const_name(item['name'], prefix)} = {item['value']};")

def gen_enum(decl, prefix):
    l(f"pub const {as_zig_type(decl['name'])} = extern enum(i32) {{")
    for item in decl['items']:
        item_name = as_enum_item_name(item['name'])
        if item_name != "FORCE_U32":
            if 'value' in item:
                l(f"    {item_name} = {item['value']},")
            else:
                l(f"    {item_name},")
    l("};")

def gen_func_c(decl, prefix):
    l(f"pub extern fn {decl['name']}({funcdecl_args_c(decl)}) {funcdecl_res_c(decl)};")

def gen_func_zig(decl, prefix):
    l("// FIXME: zig function wrapper")

def gen_helper_funcs(inp):
    if inp['module'] == 'sokol_gfx':
        l('fn init_with(target_ptr: anytype, opts: anytype) void {')
        l('    switch (@typeInfo(@TypeOf(target_ptr.*))) {')
        l('        .Array => {')
        l('            inline for (opts) |item, i| {')
        l('                init_with(&target_ptr.*[i], opts[i]);')
        l('            }')
        l('        },')
        l('        .Struct => {')
        l('            inline for (@typeInfo(@TypeOf(opts)).Struct.fields) |field| {')
        l('                init_with(&@field(target_ptr.*, field.name), @field(opts, field.name));')
        l('            }')
        l('        },')
        l('        else => {')
        l('            target_ptr.* = opts;')
        l('        }')
        l('    }')
        l('}')

def pre_parse(inp):
    global struct_types
    global enum_types
    for decl in inp['decls']:
        kind = decl['kind']
        if kind == 'struct':
            struct_types.append(decl['name'])
            if struct_is_c_compatible(decl):
                c_struct_types.append(decl['name'])
        elif kind == 'enum':
            enum_name = decl['name']
            enum_types.append(enum_name)
            enum_items[enum_name] = []
            for item in decl['items']:
                enum_items[enum_name].append(as_enum_item_name(item['name']))

def gen_module(inp):
    l('// machine generated, do not edit')
    l('')
    l('//--- helper functions ---')
    gen_helper_funcs(inp)
    pre_parse(inp)
    l('//--- API declarations ---')
    prefix = inp['prefix']
    for decl in inp['decls']:
        kind = decl['kind']
        if kind == 'struct':
            gen_struct(decl, prefix)
        elif kind == 'consts':
            gen_consts(decl, prefix)
        elif kind == 'enum':
            gen_enum(decl, prefix)
        elif kind == 'func':
            gen_func_c(decl, prefix)
            gen_func_zig(decl, prefix)

def gen_zig(input_path, output_path):
    try:
        print(f">>> {input_path} => {output_path}")
        with open(input_path, 'r') as f_inp:
            inp = json.load(f_inp)
            gen_module(inp)
            with open(output_path, 'w') as f_outp:
                f_outp.write(out_lines)
    except EnvironmentError as err:
        print(f"{err}")

def main():
    gen_zig('sokol_gfx.json', 'sokol_gfx.zig')

if __name__ == '__main__':
    main()