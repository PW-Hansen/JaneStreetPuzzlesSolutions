"""Equation formatting, region colors, canvas math, and PNG export."""

import ast
import ctypes
import re
import struct
import sys
import zlib
from fractions import Fraction


def format_candidates(values):
    """Compact consecutive candidate values into ranges."""
    numbers = sorted(values)
    if not numbers:
        return "None"
    if any(Fraction(value).denominator != 1 for value in numbers):
        return ", ".join(str(value) for value in numbers)
    parts = []
    start = previous = numbers[0]
    for value in numbers[1:] + [None]:
        if value is not None and value == previous + 1:
            previous = value
            continue
        parts.append(str(start) if start == previous else f"{start}–{previous}")
        start = previous = value
    return ", ".join(parts)


def region_colors(size, labels):
    """Greedy coloring of the region adjacency graph, with preferred colors."""
    palette = ['#f6d797', '#cab5ec', '#9cd7ed', '#efa5a5', '#efc394', '#a9d8af',
               '#e7afd4', '#b8c9ef', '#d9d79f']
    adjacency = {number: set() for number in labels.values()}
    for cell, number in labels.items():
        row, column = divmod(cell, size)
        for neighbor in (cell+1 if column+1 < size else -1,
                         cell+size if row+1 < size else -1):
            if neighbor in labels and labels[neighbor] != number:
                adjacency[number].add(labels[neighbor])
                adjacency[labels[neighbor]].add(number)
    colors = {}
    for number in sorted(adjacency, reverse=True):
        used = {colors[neighbor] for neighbor in adjacency[number] if neighbor in colors}
        preferred = palette[(number-1) % len(palette)]
        choices = [preferred] + palette
        color = next((color for color in choices if color not in used), None)
        if color is None:
            # A distinct fallback also handles grids with many touching regions.
            color = f"#{(number * 2654435761) & 0xffffff:06x}"
            while color in used:
                color = f"#{(int(color[1:], 16)+1) & 0xffffff:06x}"
        colors[number] = color
    return colors


def rgb_png(width, height, pixels):
    """Encode RGB pixels without an extra imaging dependency."""
    if len(pixels) != width*height*3:
        raise ValueError("Invalid image dimensions.")
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    rows = b''.join(b'\x00'+pixels[row*width*3:(row+1)*width*3] for row in range(height))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))
            +chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))


def grid_picture(canvas):
    """Capture the rendered Windows canvas, cropped to its grid borders."""
    if sys.platform != 'win32':
        raise OSError("Grid picture export requires Windows.")
    from ctypes import wintypes
    user = ctypes.WinDLL('user32',use_last_error=True)
    gdi = ctypes.WinDLL('gdi32',use_last_error=True)
    signatures = [
        (user,'GetDC',[wintypes.HWND],wintypes.HDC),
        (user,'ReleaseDC',[wintypes.HWND,wintypes.HDC],ctypes.c_int),
        (gdi,'CreateCompatibleDC',[wintypes.HDC],wintypes.HDC),
        (gdi,'CreateCompatibleBitmap',[wintypes.HDC,ctypes.c_int,ctypes.c_int],wintypes.HBITMAP),
        (gdi,'SelectObject',[wintypes.HDC,wintypes.HANDLE],wintypes.HANDLE),
        (gdi,'DeleteObject',[wintypes.HANDLE],wintypes.BOOL),
        (gdi,'DeleteDC',[wintypes.HDC],wintypes.BOOL),
        (gdi,'BitBlt',[wintypes.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,
                       wintypes.HDC,ctypes.c_int,ctypes.c_int,wintypes.DWORD],wintypes.BOOL),
        (gdi,'GetDIBits',[wintypes.HDC,wintypes.HBITMAP,wintypes.UINT,wintypes.UINT,
                          ctypes.c_void_p,ctypes.c_void_p,wintypes.UINT],ctypes.c_int)]
    for library,name,args,result in signatures:
        function = getattr(library,name)
        function.argtypes,function.restype = args,result
    # Tk draws the canvas itself; PrintWindow can return success while
    # leaving a black bitmap. Finish painting, then copy its actual pixels.
    canvas.update()
    width,height = canvas.winfo_width(),canvas.winfo_height()
    hwnd = canvas.winfo_id()
    dc = user.GetDC(hwnd)
    memory = bitmap = previous = None
    try:
        memory = gdi.CreateCompatibleDC(dc)
        bitmap = gdi.CreateCompatibleBitmap(dc,width,height)
        if not dc or not memory or not bitmap: raise OSError("Could not capture grid image.")
        previous = gdi.SelectObject(memory,bitmap)
        if not gdi.BitBlt(memory,0,0,width,height,dc,0,0,0x00CC0020):
            raise OSError("Could not render grid image.")
        gdi.SelectObject(memory,previous)
        previous = None
        # BITMAPINFOHEADER with a negative height requests top-down BGRX rows.
        info = ctypes.create_string_buffer(struct.pack('<IiiHHIIiiII',40,width,-height,1,32,0,0,0,0,0,0))
        pixels = ctypes.create_string_buffer(width*height*4)
        if gdi.GetDIBits(memory,bitmap,0,height,pixels,info,0) != height:
            raise OSError("Could not read grid image pixels.")
        left,top,side = canvas.bounds
        x0,y0 = max(0,int(left)-1),max(0,int(top)-1)
        x1,y1 = min(width,int(left+side)+2),min(height,int(top+side)+2)
        raw = pixels.raw
        rgb = bytearray()
        for y in range(y0,y1):
            for x in range(x0,x1):
                offset = (y*width+x)*4
                rgb.extend((raw[offset+2],raw[offset+1],raw[offset]))
        if not any(rgb):
            raise OSError("Grid capture was blank. Keep the grid visible and try Print state again.")
        return rgb_png(x1-x0,y1-y0,bytes(rgb))
    finally:
        if previous: gdi.SelectObject(memory,previous)
        if bitmap: gdi.DeleteObject(bitmap)
        if memory: gdi.DeleteDC(memory)
        if dc: user.ReleaseDC(hwnd,dc)


def display_expression(expression):
    """Use compact mathematical notation without changing the stored input."""
    expression = re.sub(r"\s*(?:\^|\*\*)\s*(-?\d+)",
                        lambda match: match[1].translate(str.maketrans(
                            "0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")), expression)
    expression = re.sub(r"(?<=\d)\s*\*\s*(?=[a-z])", "", expression)
    return expression.replace("sqrt(", "√(").replace("cbrt(", "∛(").replace("**", "^").replace("-", "−").replace("*", "·")


def fraction_parts(expression):
    """Split a top-level quotient without changing its mathematical meaning."""
    try:
        node = ast.parse(expression.replace("^", "**"), mode="eval").body
    except (SyntaxError, ValueError):
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return inline_math(ast.unparse(node.left)), inline_math(ast.unparse(node.right))
    return None


def inline_math(expression):
    """Replace divisions anywhere in an expression with layout markers."""
    try:
        tree = ast.parse(expression.replace("^", "**"), mode="eval")
    except (ValueError, SyntaxError):
        return display_expression(expression)
    replacements = {}
    class Fractions(ast.NodeTransformer):
        def visit_Call(self, node):
            node = self.generic_visit(node)
            if (isinstance(node.func, ast.Name) and re.fullmatch(r"log_([a-z]+|\d+)", node.func.id)
                    and len(node.args) == 1 and not node.keywords):
                name = f"__fraction_{len(replacements)}__"
                replacements[name] = "〔" + node.func.id[4:] + "¦" + ast.unparse(node.args[0]) + "〕"
                return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)
            return node
        def visit_BinOp(self, node):
            node = self.generic_visit(node)
            if isinstance(node.op, ast.Div):
                name = f"__fraction_{len(replacements)}__"
                replacements[name] = "⟦" + ast.unparse(node.left) + "¦" + ast.unparse(node.right) + "⟧"
                return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)
            if isinstance(node.op, ast.Pow):
                name = f"__fraction_{len(replacements)}__"
                base = ast.unparse(node.left)
                if isinstance(node.left, (ast.BinOp, ast.UnaryOp)) or (
                        isinstance(node.left, ast.Name) and node.left.id in replacements):
                    base = "(" + base + ")"
                replacements[name] = "〖" + base + "¦" + ast.unparse(node.right) + "〗"
                return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)
            return node
    text = ast.unparse(Fractions().visit(tree))
    for name, replacement in reversed(list(replacements.items())):
        text = text.replace(name, replacement)
    return display_expression(text)


def math_runs(text):
    """Separate radical arguments from surrounding text, including nested roots."""
    runs = []
    while text:
        root_start, cube_start, fraction_start, power_start, log_start = text.find("√("), text.find("∛("), text.find("⟦"), text.find("〖"), text.find("〔")
        candidates = [start for start in (root_start, cube_start, fraction_start, power_start, log_start) if start >= 0]
        start = min(candidates) if candidates else -1
        if start < 0:
            runs.append(("text", text))
            break
        is_fraction = start == fraction_start
        is_power = start == power_start
        is_log = start == log_start
        paired = is_fraction or is_power or is_log
        opening, closing = ("⟦", "⟧") if is_fraction else ("〖", "〗") if is_power else ("〔", "〕") if is_log else ("(", ")")
        depth, end = 1, start + (1 if paired else 2)
        separator = None
        while end < len(text) and depth:
            if paired and text[end] == "¦" and depth == 1:
                separator = end
            depth += (text[end] == opening) - (text[end] == closing)
            end += 1
        if depth:
            runs.append(("text", text))
            break
        if start:
            runs.append(("text", text[:start]))
        if paired:
            runs.append(("fraction" if is_fraction else "power" if is_power else "log", (math_runs(text[start+1:separator]), math_runs(text[separator+1:end-1]))))
        else:
            runs.append(("cube_root" if start == cube_start else "root", math_runs(text[start+2:end-1])))
        text = text[end:]
    return runs


def math_width(runs, font):
    return sum(font.measure(value) if kind == "text" else
               max(math_width(part, font) for part in value) + 6 if kind == "fraction" else
               math_width(value[0], font) + 0.85 * math_width(value[1], font) if kind == "power" else
               font.measure("log ") + 0.85 * math_width(value[0], font) + math_width(value[1], font) if kind == "log" else
               font.measure("3")*0.55 + font.measure("√") + 4 + math_width(value, font) if kind == "cube_root" else
               font.measure("√") + 4 + math_width(value, font) for kind, value in runs)


def draw_math(canvas, center_x, center_y, text, font):
    runs = math_runs(text)
    font_spec = ("Times New Roman", font.cget("size"), "italic")
    height = font.metrics("linespace")
    def draw(parts, left, y, scale=1):
        font_spec = ("Times New Roman", max(6, round(font.cget("size")*scale)), "italic")
        local_height = height * scale
        for kind, value in parts:
            if kind == "text":
                canvas.create_text(left, y, text=value, anchor="w", font=font_spec, fill="#252525")
                left += font.measure(value) * scale
            elif kind == "power":
                base_width = math_width(value[0], font) * scale
                draw(value[0], left, y, scale)
                draw(value[1], left+base_width, y-local_height*0.42, scale*0.85)
                left += base_width + math_width(value[1], font)*scale*0.85
            elif kind == "log":
                canvas.create_text(left, y, text="log", anchor="w",
                                   font=("Times New Roman", max(6, round(font.cget("size")*scale))), fill="#252525")
                left += font.measure("log")*scale
                draw(value[0], left, y+local_height*0.3, scale*0.85)
                left += math_width(value[0], font)*scale*0.85 + font.measure(" ")*scale
                draw(value[1], left, y, scale)
                left += math_width(value[1], font)*scale
            elif kind == "fraction":
                width = (max(math_width(part, font) for part in value) + 6)*scale
                for part, offset in ((value[0], -local_height*0.8), (value[1], local_height*0.8)):
                    draw(part, left+(width-math_width(part, font)*scale)/2, y+offset, scale)
                canvas.create_line(left, y, left+width, y, fill="#252525", width=1)
                left += width
            else:
                if kind == "cube_root":
                    canvas.create_text(left, y-local_height*0.48, text="3", anchor="w",
                                       font=("Times New Roman", max(6, round(font.cget("size")*scale*0.65))), fill="#252525")
                    left += font.measure("3")*scale*0.55
                root_width = font.measure("√")*scale
                argument_width = math_width(value, font)*scale
                # Draw the radical and vinculum as one continuous stroke.
                bar_y = y - local_height * 0.46
                canvas.create_line(left, y, left+root_width*0.28, y-local_height*0.08,
                                   left+root_width*0.52, y+local_height*0.35,
                                   left+root_width, bar_y,
                                   left+root_width+argument_width+4, bar_y,
                                   fill="#252525", width=1)
                draw(value, left+root_width+2, y, scale)
                left += root_width+argument_width+4
        return left
    draw(runs, center_x - math_width(runs, font)/2, center_y)
