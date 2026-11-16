"""识别手柄界面的矩形选中框。"""

import cv2
import numpy as np
from cv2.typing import MatLike

from one_dragon.base.geometry.rectangle import Rect


def find_focus_rects(image: MatLike, region: Rect, min_value: int = 160,
                     allow_top_protrusion: bool = False) -> list[Rect]:
    """在指定导航区域内识别黄色或黄绿色选中框。

    同时检查外形和四条边，排除图标、文字以及大块场景颜色。
    """
    crop = image[region.y1:region.y2, region.x1:region.x2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (25, 180, min_value), (42, 255, 255))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    result: list[Rect] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width < 60 or height < 28:
            continue
        # 中段边缘避开圆角，四边连续才视为选中框。
        tile = mask[y:y + height, x:x + width]
        x1, x2 = width // 4, width * 3 // 4
        y1, y2 = height // 4, height * 3 // 4
        edges = (tile[:6, x1:x2], tile[-6:, x1:x2], tile[y1:y2, :6], tile[y1:y2, -6:])
        if any(np.count_nonzero(edge) < edge.size * 0.4 for edge in edges):
            # 大卡牌右上角的等级圆圈突出矩形，矩形边线位于轮廓内侧。
            if width < 150 or height < 200:
                continue
            card_edges = ((tile[:40, x1:x2], 1), (tile[-40:, x1:x2], 1),
                          (tile[y1:y2, :40], 0), (tile[y1:y2, -40:], 0))
            # 武备卡顶部是突出的圆形图标，仍要求左右边及带小页脚的底边连续。
            if allow_top_protrusion:
                card_edges = card_edges[1:]
            if any(np.max(np.count_nonzero(edge, axis=axis)) < edge.shape[axis] * (.75 if allow_top_protrusion else .8)
                   for edge, axis in card_edges):
                continue
        result.append(Rect(x + region.x1, y + region.y1,
                           x + width + region.x1, y + height + region.y1))
    return result
