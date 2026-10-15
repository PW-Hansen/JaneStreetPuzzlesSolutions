"""Common geometry for the canvas and PNG renderer."""
from .constants import CELL_SIZE, MARGIN, COLORS


def draw(data, rectangle, line, text, selected=None):
    rows, cols = data['rows'], data['cols']
    s, m = CELL_SIZE, MARGIN
    for r in range(rows):
        for c in range(cols):
            x, y = m+c*s, m+r*s
            rectangle((x, y, x+s, y+s), COLORS[data['colors'].get(f'{r},{c}', 0)])
    for r in range(rows+1):
        line((m, m+r*s, m+cols*s, m+r*s), '#777777', 1)
    for c in range(cols+1):
        line((m+c*s, m, m+c*s, m+rows*s), '#777777', 1)
    analysis = data.get('analysis')
    confirmed_borders = dict(data['borders'])
    if analysis:
        confirmed_borders.update(analysis.get('canonical_borders', {}))
    for key in confirmed_borders:
        axis, r, c = key.split(',')
        x, y = m+int(c)*s, m+int(r)*s
        line((x, y, x+s if axis == 'h' else x, y+s if axis == 'v' else y), 'black', 5)
    for points in ((m,m,m+cols*s,m), (m,m,m,m+rows*s), (m+cols*s,m,m+cols*s,m+rows*s), (m,m+rows*s,m+cols*s,m+rows*s)):
        line(points, 'black', 5)
    if analysis and analysis['preview'] >= 0:
        for key in analysis['candidates'][analysis['preview']]:
            if key in confirmed_borders:
                continue
            axis, r, c = key.split(',')
            x, y = m+int(c)*s, m+int(r)*s
            line((x, y, x+s if axis == 'h' else x, y+s if axis == 'v' else y), '#7040b0', 3)
    if selected is not None:
        r, c = selected
        x, y = m+c*s, m+r*s
        for points in ((x+4,y+4,x+s-4,y+4), (x+4,y+4,x+4,y+s-4), (x+s-4,y+4,x+s-4,y+s-4), (x+4,y+s-4,x+s-4,y+s-4)):
            line(points, '#1769bd', 3)
    for key, value in data['entries'].items():
        r, c = map(int, key.split(','))
        text((m+(c+.5)*s, m+(r+.5)*s), value, 'black' if value.isdecimal() else '#c62828')


def export_png(path, data, selected=None):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (2*MARGIN+data['cols']*CELL_SIZE, 2*MARGIN+data['rows']*CELL_SIZE), 'white')
    painter = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 23)
    except OSError:
        font = ImageFont.load_default(size=23)
    draw(data, lambda box, color: painter.rectangle(box, fill=color),
         lambda points, color, width: painter.line(points, fill=color, width=width),
         lambda pos, value, color: painter.text(pos, value, fill=color, font=font, anchor='mm'), selected)
    image.save(path)
