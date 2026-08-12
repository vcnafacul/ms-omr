"""Renderiza um cartão sintético a partir do template.json gerado pelo ms-simulado.

O template.json vive no espaço normalizado pelos markers (pageDimensions = caixa dos
centros de marker). A imagem sintética é em espaço A4; o CropOnMarkers do OMRChecker
normaliza de volta. Para uma bolha, o centro visual A4 = origin_topleft(template) +
índices·gaps + bubbleDim/2 + near, onde near = (A4 − markerBox)/2.
"""

import json
import re
from pathlib import Path

import cv2
import numpy as np

A4_W, A4_H = 2480, 3508


def render_synthetic_card(fixture_dir: Path, marcas: dict) -> np.ndarray:
    tpl = json.loads((fixture_dir / "template.json").read_text())
    box_w, box_h = tpl["pageDimensions"]
    near_x = (A4_W - box_w) // 2
    near_y = (A4_H - box_h) // 2
    bw, bh = tpl["bubbleDimensions"]
    half_w, half_h = bw / 2, bh / 2
    r = int(min(bw, bh) / 2) - 4

    img = np.full((A4_H, A4_W, 3), 255, np.uint8)

    # markers: centro em (near, near), (A4_W-near, near), ...
    marker = cv2.imread(str(fixture_dir / "omr_marker.png"))
    mh, mw = marker.shape[:2]
    centers = [
        (near_x, near_y),
        (A4_W - near_x, near_y),
        (near_x, A4_H - near_y),
        (A4_W - near_x, A4_H - near_y),
    ]
    for cx, cy in centers:
        x0, y0 = int(cx - mw / 2), int(cy - mh / 2)
        img[y0 : y0 + mh, x0 : x0 + mw] = marker

    def fill_a4(sample_center_x, sample_center_y):
        cx = int(sample_center_x + near_x)
        cy = int(sample_center_y + near_y)
        cv2.circle(img, (cx, cy), r, (0, 0, 0), -1)

    fb = tpl["fieldBlocks"]

    # matrícula (QTYPE_INT vertical): topleft(i,d) = origin + (i·labelsGap, d·bubblesGap)
    if "matricula" in marcas:
        m = fb["matricula"]
        ox, oy = m["origin"]
        for i, d in enumerate(marcas["matricula"]):
            fill_a4(ox + i * m["labelsGap"] + half_w, oy + d * m["bubblesGap"] + half_h)

    # respostas (QTYPE_MCQ5 horizontal): topleft(q,o) = origin + (o·bubblesGap, qLocal·labelsGap)
    for key, block in fb.items():
        if not key.startswith("respostas_c"):
            continue
        mo = re.match(r"[a-z]+(\d+)\.\.(\d+)", block["fieldLabels"][0])
        first, last = int(mo.group(1)), int(mo.group(2))
        ox, oy = block["origin"]
        for q in range(first, last + 1):
            kq = f"q{q}"
            if kq in marcas:
                o = marcas[kq]
                i_local = q - first
                fill_a4(
                    ox + o * block["bubblesGap"] + half_w,
                    oy + i_local * block["labelsGap"] + half_h,
                )

    return img
