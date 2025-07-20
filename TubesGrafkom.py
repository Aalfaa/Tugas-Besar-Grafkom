import pygame
import numpy as np
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

WIDTH, HEIGHT = 800, 600
BG_COLOR = (0.1, 0.1, 0.1, 1.0)
COLORS = {
    "red": (1, 0, 0),
    "green": (0, 1, 0),
    "blue": (0, 0, 1),
    "yellow": (1, 1, 0),
    "cyan": (0, 1, 1),
    "magenta": (1, 0, 1),
    "white": (1, 1, 1),
}

current_mode = "2D"
objects_2d: list = []
current_type = None
current_color = COLORS["red"]
line_thickness = 1.0

drawing = False
polygon_points = []

window_clipping = []
window_action = None
last_mouse_pos = None

selected_object = None
transform_mode = None

line_pivot = None
line_unit_dir = (0.0, 0.0)
line_init_len = 0.0

cube = None
camera_pos = [0, 0, 5]
camera_target = [0, 0, 0]
camera_up = [0, 1, 0]

def is_transforming() -> bool:
    return transform_mode in ("Translasi", "rotate", "scale")

class Point2D:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

class Object2D:
    def __init__(self, obj_type: str, points: list[Point2D], color, thickness=1.0):
        self.obj_type = obj_type
        self.points = points                             
        self.original_points = [Point2D(p.x, p.y) for p in points]
        self.color = color
        self.original_color = color
        self.thickness = thickness
        self.translation = [0.0, 0.0]
        self.rotation = 0.0                               
        self.scale = [1.0, 1.0]

    # --------- gambar ----------
    def draw(self):
        if len(self.points) == 0:
            return
        if self.obj_type == "line" and len(self.points) < 2:
            return

        glColor3fv(self.color)
        glLineWidth(self.thickness)

        # Garis digambar langsung (tanpa matrix) supaya pivot‑transform mudah
        if self.obj_type == "line":
            glBegin(GL_LINES)
            for p in self.points:
                glVertex2f(p.x, p.y)
            glEnd()
            return

        glPushMatrix()
        glTranslatef(*self.translation, 0)
        glRotatef(self.rotation, 0, 0, 1)
        glScalef(*self.scale, 1)

        if self.obj_type == "point":
            if len(self.points) >= 1:
                glBegin(GL_POINTS)
                glVertex2f(self.points[0].x, self.points[0].y)
                glEnd()
            glPopMatrix()
            return

        elif self.obj_type == "square":
            if len(self.points) < 2:
                glPopMatrix()
                return

            # hitung pusat & setengah sisi
            p1, p2 = self.points
            cx = (p1.x + p2.x) / 2.0
            cy = (p1.y + p2.y) / 2.0
            hw = abs(p2.x - p1.x) / 2.0
            hh = abs(p2.y - p1.y) / 2.0

            # transform khusus kotak
            glPopMatrix()
            glPushMatrix()
            glTranslatef(cx + self.translation[0], cy + self.translation[1], 0)
            glRotatef(self.rotation, 0, 0, 1)
            glScalef(*self.scale, 1)

            glBegin(GL_LINE_LOOP)
            glVertex2f(-hw, -hh)
            glVertex2f(hw, -hh)
            glVertex2f(hw, hh)
            glVertex2f(-hw, hh)
            glEnd()

            glPopMatrix()
            return

        elif self.obj_type == "ellipse":
            if len(self.points) < 2:
                glPopMatrix()
                return
            center, radius = self.points

            # transform khusus elips
            glPopMatrix()
            glPushMatrix()
            glTranslatef(center.x + self.translation[0], center.y + self.translation[1], 0)
            glRotatef(self.rotation, 0, 0, 1)
            glScalef(*self.scale, 1)

            glBegin(GL_LINE_LOOP)
            for i in range(100):
                ang = 2 * np.pi * i / 100
                glVertex2f(radius.x * np.cos(ang), radius.y * np.sin(ang))
            glEnd()
            glPopMatrix()
            return

    def bounding_box(self):
        xs = [p.x for p in self.original_points]
        ys = [p.y for p in self.original_points]
        return min(xs), min(ys), max(xs), max(ys)

class Cube3D:
    def __init__(self):
        self.vertices = [
            [1, 1, 1], [1, 1, -1], [1, -1, 1], [1, -1, -1],
            [-1, 1, 1], [-1, 1, -1], [-1, -1, 1], [-1, -1, -1]
        ]
        self.faces = [
            [0, 1, 3, 2], [4, 5, 7, 6], [0, 1, 5, 4],
            [2, 3, 7, 6], [0, 2, 6, 4], [1, 3, 7, 5]
        ]
        self.colors = [
            [1, 0, 0], [0, 1, 0], [0, 0, 1],
            [1, 1, 0], [1, 0, 1], [0, 1, 1]
        ]
        self.rotation = [0, 0, 0]
        self.translation = [0, 0, 0]

    def draw(self):
        glPushMatrix()
        glTranslatef(*self.translation)
        glRotatef(self.rotation[0], 1, 0, 0)
        glRotatef(self.rotation[1], 0, 1, 0)
        glRotatef(self.rotation[2], 0, 0, 1)
        glBegin(GL_QUADS)
        for i, face in enumerate(self.faces):
            glColor3fv(self.colors[i])
            for v in face:
                glVertex3fv(self.vertices[v])
        glEnd()
        glPopMatrix()

def apply_window_scissor():
    if len(window_clipping) != 2:
        glDisable(GL_SCISSOR_TEST)
        return

    p1, p2 = window_clipping
    xmin, ymin = min(p1.x, p2.x), min(p1.y, p2.y)
    xmax, ymax = max(p1.x, p2.x), max(p1.y, p2.y)

    # --- dunia ➜ pixel ---
    x_px = int((xmin + 10) / 20 * WIDTH)
    y_px = int((ymin + 10) / 20 * HEIGHT)       
    w_px = int((xmax - xmin) / 20 * WIDTH)
    h_px = int((ymax - ymin) / 20 * HEIGHT)

    glEnable(GL_SCISSOR_TEST)
    glScissor(x_px, y_px, max(1, w_px), max(1, h_px))

def draw_grid():
    prev = glGetFloatv(GL_LINE_WIDTH)
    glColor3f(0.3, 0.3, 0.3)
    glLineWidth(1)
    glBegin(GL_LINES)
    for i in range(-10, 11):
        glVertex2f(i, -10)
        glVertex2f(i, 10)
        glVertex2f(-10, i)
        glVertex2f(10, i)
    glEnd()
    glLineWidth(prev)

def draw_window_clipping():
    if len(window_clipping) == 2:
        p1, p2 = window_clipping
        glColor3f(1, 1, 0)
        glLineWidth(2)
        glBegin(GL_LINE_LOOP)
        glVertex2f(p1.x, p1.y)
        glVertex2f(p2.x, p1.y)
        glVertex2f(p2.x, p2.y)
        glVertex2f(p1.x, p2.y)
        glEnd()
        glLineWidth(1)

def cohen_sutherland_clip(x0, y0, x1, y1, xmin, ymin, xmax, ymax):
    INSIDE, LEFT, RIGHT, BOTTOM, TOP = 0, 1, 2, 4, 8

    def code(x, y):
        c = INSIDE
        if x < xmin:
            c |= LEFT
        elif x > xmax:
            c |= RIGHT
        if y < ymin:
            c |= BOTTOM
        elif y > ymax:
            c |= TOP
        return c

    c0, c1 = code(x0, y0), code(x1, y1)
    while True:
        if not (c0 | c1):
            return x0, y0, x1, y1
        if c0 & c1:
            return None
        c_out = c0 if c0 else c1
        if c_out & TOP:
            x = x0 + (x1 - x0) * (ymax - y0) / (y1 - y0)
            y = ymax
        elif c_out & BOTTOM:
            x = x0 + (x1 - x0) * (ymin - y0) / (y1 - y0)
            y = ymin
        elif c_out & RIGHT:
            y = y0 + (y1 - y0) * (xmax - x0) / (x1 - x0)
            x = xmax
        else:  # LEFT
            y = y0 + (y1 - y0) * (xmin - x0) / (x1 - x0)
            x = xmin
        if c_out == c0:
            x0, y0 = x, y
            c0 = code(x0, y0)
        else:
            x1, y1 = x, y
            c1 = code(x1, y1)

def clip_objects():
    if len(window_clipping) != 2:
        for obj in objects_2d:
            obj.points = [Point2D(p.x, p.y) for p in obj.original_points]
            obj.color = obj.original_color
        return

    p1, p2 = window_clipping
    xmin, ymin = min(p1.x, p2.x), min(p1.y, p2.y)
    xmax, ymax = max(p1.x, p2.x), max(p1.y, p2.y)

    for obj in objects_2d:
        obj.points = [Point2D(p.x, p.y) for p in obj.original_points]
        obj.color = obj.original_color

        # ---------- LINE ----------
        if obj.obj_type == "line":
            p0, p1_ = obj.original_points
            clip = cohen_sutherland_clip(
                p0.x, p0.y, p1_.x, p1_.y, xmin, ymin, xmax, ymax
            )
            if clip:
                x0, y0, x1_, y1_ = clip
                obj.points = [Point2D(x0, y0), Point2D(x1_, y1_)]
                inside0 = xmin <= p0.x <= xmax and ymin <= p0.y <= ymax
                inside1 = xmin <= p1_.x <= xmax and ymin <= p1_.y <= ymax
                obj.color = (
                    COLORS["green"] if inside0 and inside1 else obj.original_color
                )
            else:
                obj.points = []

        # ---------- BENTUK LAIN ----------
        elif obj.obj_type in ("square", "ellipse", "polygon", "point"):
            bxmin, bymin, bxmax, bymax = obj.bounding_box()
            if bxmax < xmin or bxmin > xmax or bymax < ymin or bymin > ymax:
                obj.points = []               
            else:
                if xmin <= bxmin and bxmax <= xmax and ymin <= bymin and bymax <= ymax:
                    obj.color = COLORS["green"]

def mouse_to_world(mx, my):
    return (mx / WIDTH) * 20 - 10, 10 - (my / HEIGHT) * 20

def point_inside_window(x, y):
    if len(window_clipping) != 2:
        return False
    p1, p2 = window_clipping
    xmin, ymin = min(p1.x, p2.x), min(p1.y, p2.y)
    xmax, ymax = max(p1.x, p2.x), max(p1.y, p2.y)
    return xmin <= x <= xmax and ymin <= y <= ymax

def near_corner(x, y, corner, th=0.5):
    return abs(x - corner.x) <= th and abs(y - corner.y) <= th

def point_near_line(px, py, x1, y1, x2, y2, th=0.5) -> bool:
    seg_len = np.hypot(x2 - x1, y2 - y1)
    if seg_len == 0:
        return np.hypot(px - x1, py - y1) < th
    u = ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / seg_len**2
    u = max(0, min(1, u))
    projx = x1 + u * (x2 - x1)
    projy = y1 + u * (y2 - y1)
    return np.hypot(px - projx, py - projy) < th

def select_object(mx, my):
    wx, wy = mouse_to_world(mx, my)
    for obj in reversed(objects_2d):
        if not obj.points:
            continue
        if obj.obj_type == "point":
            p = obj.points[0]
            if abs(p.x - wx) < 0.5 and abs(p.y - wy) < 0.5:
                return obj
        elif obj.obj_type == "line":
            p1, p2 = obj.points
            if point_near_line(wx, wy, p1.x, p1.y, p2.x, p2.y):
                return obj
        else:
            xs = [p.x for p in obj.points]
            ys = [p.y for p in obj.points]
            if min(xs) <= wx <= max(xs) and min(ys) <= wy <= max(ys):
                return obj
    return None

def init():
    pygame.init()
    pygame.font.init()
    pygame.display.set_mode((WIDTH, HEIGHT), DOUBLEBUF | OPENGL)
    pygame.display.set_caption("Project UAS Grafika Komputer I | 202310370311436 - 202310370311433")
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluOrtho2D(-10, 10, -10, 10)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    glClearColor(*BG_COLOR)
    glPointSize(5)
    glLineWidth(1)

def init_3d():
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glLightfv(GL_LIGHT0, GL_POSITION, [2, 5, 2, 1])
    glLightfv(GL_LIGHT0, GL_DIFFUSE, [1, 1, 1, 1])
    glLightfv(GL_LIGHT0, GL_AMBIENT, [0.2, 0.2, 0.2, 1])
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT, GL_AMBIENT_AND_DIFFUSE)

def draw_text(x, y, txt, font):
    """
    Gambar teks di window‑coords; transparansi dihormati.
    """
    surf = font.render(txt, True, (255, 255, 255))
    surf = surf.convert_alpha()
    w, h = surf.get_size()

    data = pygame.image.tostring(surf, "RGBA", True)
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    glWindowPos2f(x, y)
    glDrawPixels(w, h, GL_RGBA, GL_UNSIGNED_BYTE, data)

    glDisable(GL_BLEND)

def draw_ui():
    depth_on = glIsEnabled(GL_DEPTH_TEST)
    light_on = glIsEnabled(GL_LIGHTING)
    if depth_on:
        glDisable(GL_DEPTH_TEST)
    if light_on:
        glDisable(GL_LIGHTING)

    font = pygame.font.SysFont("Arial", 18)

    color_name = next(
        (name for name, rgb in COLORS.items() if rgb == current_color),
        str(list(current_color))
    )
    status = (
        f"Mode: {current_mode}   |   Objek: {current_type or '-'}   |   "
        f"Warna: {(color_name)}"
        + (f"   |   Tebal: {line_thickness}" if current_mode == "2D" else "")
        + (f"   |   Transformasi: {transform_mode}" if transform_mode else "")
        + "   |   H: Bantuan"
    )
    draw_text(10, HEIGHT - 25, status, font)

    if show_help:
        help_lines = [
            "Bantuan Tombol",
            "MODE         :  F1 → 2D   |   F2 → 3D",
            "2D           :  P  Titik   |  L  Garis   |  S  Persegi   |  E  Lingkaran   |  G  Polygon   |  W  Clip‑Window",
            "WARNA (1‑6)  :  1 R  2 G  3 B  4 Y  5 C  6 M",
            "TRANFORMASI  :  T Translasi   |  R Rotasi   |  Z Scaling",
            "LAIN         :  + / –  Ketebalan Garis   |  C  Hapus   |  H  Help",
            "3D Cube      :  Left‑Drag Rotasi   |  Right‑Drag Translasi",
            "",
            "ESC → batal transform",
        ]
        y = HEIGHT - 50
        for ln in help_lines:
            draw_text(10, y, ln, font)
            y -= 22

    if depth_on:
        glEnable(GL_DEPTH_TEST)
    if light_on:
        glEnable(GL_LIGHTING)

def main():
    global current_mode, current_type, drawing, polygon_points
    global current_color, line_thickness, window_clipping
    global selected_object, transform_mode, cube, window_action, last_mouse_pos
    global line_pivot, line_unit_dir, line_init_len, show_help

    init()
    cube = Cube3D()
    show_help = False

    while True:
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                return

            # ---------------- KEYBOARD ----------------
            if event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    transform_mode = None
                    selected_object = None
                elif event.key == K_h:
                    show_help = not show_help
                elif event.key == K_F1:
                    current_mode = "2D"
                    transform_mode = None
                    glMatrixMode(GL_PROJECTION)
                    glLoadIdentity()
                    gluOrtho2D(-10, 10, -10, 10)
                    glDisable(GL_LIGHTING)
                    glDisable(GL_DEPTH_TEST)
                    init()
                elif event.key == K_F2:
                    current_mode = "3D"
                    transform_mode = None
                    glMatrixMode(GL_PROJECTION)
                    glLoadIdentity()
                    gluPerspective(45, WIDTH / HEIGHT, 0.1, 50)
                    glMatrixMode(GL_MODELVIEW)
                    glLoadIdentity()
                    init_3d()
                elif current_mode == "2D":
                    if event.key == K_p:
                        current_type = "point"
                        transform_mode = None
                    elif event.key == K_l:
                        current_type = "line"
                        transform_mode = None
                    elif event.key == K_s:
                        current_type = "square"
                        transform_mode = None
                    elif event.key == K_e:
                        current_type = "ellipse"
                        transform_mode = None
                    elif event.key == K_g:
                        current_type = "polygon"
                        transform_mode = None
                    elif event.key == K_w:
                        window_clipping.clear()
                        clip_objects()
                        current_type = "window"
                        transform_mode = None
                    elif event.key == K_c:
                        objects_2d.clear()
                        polygon_points.clear()
                        transform_mode = None
                    elif event.key in (K_1, K_2, K_3, K_4, K_5, K_6):
                        key_map = {
                            K_1: "red",
                            K_2: "green",
                            K_3: "blue",
                            K_4: "yellow",
                            K_5: "cyan",
                            K_6: "magenta",
                        }
                        current_color = COLORS[key_map[event.key]]
                    elif event.key in (K_EQUALS, K_PLUS):
                        line_thickness = min(10, line_thickness + 0.5)
                    elif event.key == K_MINUS:
                        line_thickness = max(0.5, line_thickness - 0.5)
                    elif event.key == K_t:
                        transform_mode = "Translasi"
                    elif event.key == K_r:
                        transform_mode = "rotate"
                    elif event.key == K_z:
                        transform_mode = "scale"

            # ---------------- MOUSE DOWN ----------------
            if event.type == MOUSEBUTTONDOWN:
                mx, my = pygame.mouse.get_pos()
                wx, wy = mouse_to_world(mx, my)

                # Window drag/resize
                if (
                    current_mode == "2D"
                    and len(window_clipping) == 2
                    and current_type != "window"
                    and event.button == 1
                ):
                    p1, p2 = window_clipping
                    c = {
                        "tl": Point2D(min(p1.x, p2.x), max(p1.y, p2.y)),
                        "tr": Point2D(max(p1.x, p2.x), max(p1.y, p2.y)),
                        "bl": Point2D(min(p1.x, p2.x), min(p1.y, p2.y)),
                        "br": Point2D(max(p1.x, p2.x), min(p1.y, p2.y)),
                    }
                    if near_corner(wx, wy, c["tl"]):
                        window_action = "resize_tl"
                    elif near_corner(wx, wy, c["tr"]):
                        window_action = "resize_tr"
                    elif near_corner(wx, wy, c["bl"]):
                        window_action = "resize_bl"
                    elif near_corner(wx, wy, c["br"]):
                        window_action = "resize_br"
                    elif point_inside_window(wx, wy):
                        window_action = "move"
                    if window_action:
                        last_mouse_pos = (wx, wy)
                        continue

                # --- Objek / window creation ---
                if current_mode == "2D" and event.button == 1:
                    # Bikin objek baru (jika tidak sedang transform)
                    if not is_transforming():
                        if current_type == "point":
                            objects_2d.append(
                                Object2D("point", [Point2D(wx, wy)], current_color, line_thickness)
                            )
                        elif current_type in ("line", "square", "ellipse", "polygon"):
                            if not drawing:
                                drawing = True
                                polygon_points = [Point2D(wx, wy)]
                            else:
                                polygon_points.append(Point2D(wx, wy))
                                if current_type == "line" and len(polygon_points) == 2:
                                    objects_2d.append(
                                        Object2D(
                                            "line",
                                            polygon_points.copy(),
                                            current_color,
                                            line_thickness,
                                        )
                                    )
                                    drawing = False
                                    polygon_points.clear()
                                elif current_type == "square" and len(polygon_points) == 2:
                                    objects_2d.append(
                                        Object2D(
                                            "square",
                                            polygon_points.copy(),
                                            current_color,
                                            line_thickness,
                                        )
                                    )
                                    drawing = False
                                    polygon_points.clear()
                                elif current_type == "ellipse" and len(polygon_points) == 2:
                                    c = polygon_points[0]
                                    r = Point2D(
                                        abs(polygon_points[1].x - c.x),
                                        abs(polygon_points[1].y - c.y),
                                    )
                                    objects_2d.append(
                                        Object2D(
                                            "ellipse",
                                            [c, r],
                                            current_color,
                                            line_thickness,
                                        )
                                    )
                                    drawing = False
                                    polygon_points.clear()
                        elif current_type == "window":
                            if len(window_clipping) < 2:
                                window_clipping.append(Point2D(wx, wy))
                                if len(window_clipping) == 2:
                                    current_type = None
                                    clip_objects()

                    # Pemilihan objek utk transform
                    if transform_mode and not window_action:
                        selected_object = select_object(mx, my)

                        # Siapkan data pivot‑line
                        if (
                            selected_object
                            and selected_object.obj_type == "line"
                            and transform_mode in ("rotate", "scale")
                        ):
                            line_pivot = selected_object.points[0]
                            other = selected_object.points[1]
                            dx, dy = other.x - line_pivot.x, other.y - line_pivot.y
                            line_init_len = np.hypot(dx, dy)
                            if line_init_len > 0:
                                line_unit_dir = (dx / line_init_len, dy / line_init_len)
                            else:
                                line_unit_dir = (1, 0)

                # Klik kanan keluar transform
                if event.button == 3:
                    transform_mode = None
                    selected_object = None

            # ---------------- MOUSE MOTION ----------------
            if event.type == MOUSEMOTION:
                mx, my = pygame.mouse.get_pos()
                wx, wy = mouse_to_world(mx, my)

                # Window move / resize
                if window_action and last_mouse_pos:
                    dx, dy = wx - last_mouse_pos[0], wy - last_mouse_pos[1]
                    p1, p2 = window_clipping
                    if window_action == "move":
                        p1.x += dx
                        p1.y += dy
                        p2.x += dx
                        p2.y += dy
                    elif window_action == "resize_tl":
                        p1.x += dx
                        p2.y += dy
                    elif window_action == "resize_tr":
                        p2.x += dx
                        p2.y += dy
                    elif window_action == "resize_bl":
                        p1.x += dx
                        p1.y += dy
                    elif window_action == "resize_br":
                        p2.x += dx
                        p1.y += dy
                    last_mouse_pos = (wx, wy)
                    clip_objects()

                # Transformasi objek
                elif pygame.mouse.get_pressed()[0] and selected_object and transform_mode:
                    if selected_object.obj_type == "line":
                        if transform_mode == "Translasi":
                            dx = (event.rel[0] / WIDTH) * 20
                            dy = -(event.rel[1] / HEIGHT) * 20
                            for p in selected_object.points:
                                p.x += dx
                                p.y += dy
                            for p in selected_object.original_points:
                                p.x += dx
                                p.y += dy
                            if line_pivot:
                                line_pivot.x += dx
                                line_pivot.y += dy
                        elif transform_mode == "rotate":
                            vx, vy = wx - line_pivot.x, wy - line_pivot.y
                            vlen = np.hypot(vx, vy)
                            if vlen > 1e-4:
                                ux, uy = vx / vlen, vy / vlen
                                new_end = Point2D(
                                    line_pivot.x + ux * line_init_len,
                                    line_pivot.y + uy * line_init_len,
                                )
                                selected_object.points[1] = new_end
                        elif transform_mode == "scale":
                            proj = (wx - line_pivot.x) * line_unit_dir[0] + (
                                wy - line_pivot.y
                            ) * line_unit_dir[1]
                            new_len = max(0.1, proj)
                            new_end = Point2D(
                                line_pivot.x + line_unit_dir[0] * new_len,
                                line_pivot.y + line_unit_dir[1] * new_len,
                            )
                            selected_object.points[1] = new_end
                    else:
                        dx = (event.rel[0] / WIDTH) * 20
                        dy = -(event.rel[1] / HEIGHT) * 20
                        if transform_mode == "Translasi":
                            selected_object.translation[0] += dx
                            selected_object.translation[1] += dy
                        elif transform_mode == "rotate" and selected_object.obj_type != "point":
                            selected_object.rotation += dx * 10
                        elif transform_mode == "scale" and selected_object.obj_type != "point":
                            selected_object.scale[0] += dx * 0.1
                            selected_object.scale[1] += dy * 0.1

                # 3‑D rotasi kamera
                if current_mode == "3D":
                    dx, dy = event.rel
                    if pygame.mouse.get_pressed()[0]:
                        cube.rotation[1] += dx * 0.5
                        cube.rotation[0] += dy * 0.5
                    elif pygame.mouse.get_pressed()[2]:
                        cube.translation[0] += dx * 0.05
                        cube.translation[1] -= dy * 0.05

            # ---------------- MOUSE UP ----------------
            if event.type == MOUSEBUTTONUP:
                window_action = None
                last_mouse_pos = None
                selected_object = None

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if current_mode == "2D":
            draw_grid()
            draw_window_clipping()
            apply_window_scissor()
            for o in objects_2d:
                o.draw()

            # --- AKTIFKAN SCISSOR JIKA ADA WINDOW KLIPING ---
            if len(window_clipping) == 2:
                p1, p2 = window_clipping
                xmin, ymin = min(p1.x, p2.x), min(p1.y, p2.y)
                xmax, ymax = max(p1.x, p2.x), max(p1.y, p2.y)

                # konversi koordinat dunia → pixel
                x_px = int((xmin + 10) / 20 * WIDTH)
                y_px = int((10 - ymax) / 20 * HEIGHT)         # OpenGL counts y from bottom
                w_px = int((xmax - xmin) / 20 * WIDTH)
                h_px = int((ymax - ymin) / 20 * HEIGHT)

                glEnable(GL_SCISSOR_TEST)
                glScissor(x_px, y_px, w_px, h_px)
            else:
                glDisable(GL_SCISSOR_TEST)

            glDisable(GL_SCISSOR_TEST)

            # Preview saat drawing
            if drawing and not is_transforming() and polygon_points:
                glColor3fv(current_color)
                glLineWidth(line_thickness)
                mx, my = pygame.mouse.get_pos()
                wx, wy = mouse_to_world(mx, my)
                if current_type == "line":
                    p = polygon_points[0]
                    glBegin(GL_LINES)
                    glVertex2f(p.x, p.y)
                    glVertex2f(wx, wy)
                    glEnd()
                elif current_type == "square":
                    p = polygon_points[0]
                    glBegin(GL_LINE_LOOP)
                    glVertex2f(p.x, p.y)
                    glVertex2f(wx, p.y)
                    glVertex2f(wx, wy)
                    glVertex2f(p.x, wy)
                    glEnd()
                elif current_type == "ellipse":
                    c = polygon_points[0]
                    rx, ry = abs(wx - c.x), abs(wy - c.y)
                    glBegin(GL_LINE_LOOP)
                    for i in range(100):
                        ang = 2 * np.pi * i / 100
                        glVertex2f(c.x + rx * np.cos(ang), c.y + ry * np.sin(ang))
                    glEnd()
                elif current_type == "polygon":
                    glBegin(GL_LINE_STRIP)
                    for p in polygon_points:
                        glVertex2f(p.x, p.y)
                    glVertex2f(wx, wy)
                    glEnd()
        else:
            glLoadIdentity()
            gluLookAt(*camera_pos, *camera_target, *camera_up)
            glDisable(GL_LIGHTING)
            glColor3f(0.4, 0.4, 0.4)
            glBegin(GL_LINES)
            for i in range(-10, 11, 2):
                glVertex3f(i, 0, -10)
                glVertex3f(i, 0, 10)
                glVertex3f(-10, 0, i)
                glVertex3f(10, 0, i)
            glEnd()
            glEnable(GL_LIGHTING)
            cube.draw()

        draw_ui()
        pygame.display.flip()
        pygame.time.wait(10)

if __name__ == "__main__":
    main()
