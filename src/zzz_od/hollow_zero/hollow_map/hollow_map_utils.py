from typing import List, Optional

import cv2
from cv2.typing import MatLike

from one_dragon.base.geometry.rectangle import Rect
from one_dragon.utils import cal_utils
from one_dragon.yolo.detect_utils import DetectFrameResult
from zzz_od.context.zzz_context import ZContext
from zzz_od.hollow_zero.game_data.hollow_zero_event import HollowZeroEntry
from zzz_od.hollow_zero.hollow_map.hollow_zero_map import HollowZeroMap, HollowZeroMapNode


def construct_map_from_yolo_result(
        ctx: ZContext,
        detect_result: DetectFrameResult,
        name_2_entry: dict[str, HollowZeroEntry]
) -> Optional[HollowZeroMap]:
    """
    根据识别结果构造地图
    """
    nodes: List[HollowZeroMapNode] = []
    unknown = name_2_entry['未知']

    for result in detect_result.results:
        entry_name = result.detect_class.class_name[5:]
        if entry_name in name_2_entry:
            entry = name_2_entry[entry_name]
        else:
            entry = unknown

        width = result.x2 - result.x1
        height = result.y2 - result.y1
        if entry.is_base:
            pos = Rect(result.x1, result.y2 - width, result.x2, result.y2)
        else:
            pos = Rect(result.x1, result.y1, result.x2, result.y2 + height // 3)

        # 判断与已有的节点是否重复
        to_merge: Optional[HollowZeroMapNode] = None
        for existed in nodes:
            min_dis = min(pos.height, pos.width, existed.pos.height, existed.pos.width) // 2
            if cal_utils.distance_between(pos.center, existed.pos.center) < min_dis:
                to_merge = existed
                break

        if to_merge is not None:
            if to_merge.entry.is_base and not entry.is_base:  # 旧的是底座 那么将新的类型赋值上去
                to_merge.entry = entry
                to_merge.pos.y1 = pos.y1  # 使用具体类型的坐标
            elif not to_merge.entry.is_base and entry.is_base:  # 旧的是格子类型 那么把底座的范围赋值上去
                to_merge.pos.x1 = pos.x1
                to_merge.pos.x2 = pos.x2
                to_merge.pos.y2 = pos.y2
            else:
                pass
        else:
            node = HollowZeroMapNode(pos, entry,
                                     check_time=detect_result.run_time,
                                     confidence=result.score)
            nodes.append(node)

    for node in nodes:
        if node.entry.is_base:  # 只识别到底座的 赋值为未知
            node.entry = unknown

    if len(nodes) > 0:  # 有识别到节点才认为是有地图
        return construct_map_from_nodes(ctx, nodes, detect_result.run_time)
    else:
        return None


def construct_map_from_nodes(
        ctx: ZContext,
        nodes: List[HollowZeroMapNode],
        check_time: float
) -> HollowZeroMap:
    current_idx: Optional[int] = None
    for i in range(len(nodes)):
        if nodes[i].entry.entry_name == '当前':
            if current_idx is not None:
                # 当出现多个[当前]节点时 说明上一次移动可能失败了 导致内存中有一个错误的节点
                # 此时 只保留最新识别到的结果
                if nodes[current_idx].check_time < nodes[i].check_time:
                    # 将错误的[当前]节点 设置为未知 且0置信度 等待后续被识别结果覆盖
                    nodes[current_idx].entry = ctx.withered_domain.data_service.name_2_entry['未知']
                    nodes[current_idx].confidence = 0
                    current_idx = i
            else:
                current_idx = i

    edges: dict[int, List[int]] = {}

    for i in range(len(nodes)):
        node_1 = nodes[i]
        if (node_1.pos.x1 < 0
                or node_1.pos.y1 < 0
                or node_1.pos.x2 >= ctx.project_config.screen_standard_width
                or node_1.pos.y2 >= ctx.project_config.screen_standard_height
        ):
            continue

        for j in range(len(nodes)):
            node_2 = nodes[j]
            if (node_2.pos.x1 < 0
                    or node_2.pos.y1 < 0
                    or node_2.pos.x2 >= ctx.project_config.screen_standard_width
                    or node_2.pos.y2 >= ctx.project_config.screen_standard_height
            ):
                continue

            if not node_1.entry.can_go or not node_2.entry.can_go:
                continue

            if _at_left(node_1, node_2):  # 1在2左边
                if node_2.entry.entry_name in ['轨道-左']:
                    pass
                elif node_1.entry.entry_name in ['轨道-上', '轨道-下', '轨道-左']:
                    pass
                else:
                    _add_directed_edge(edges, i, j)
            elif _at_right(node_1, node_2):  # 1在2右边
                if node_2.entry.entry_name in ['轨道-右']:
                    pass
                elif node_1.entry.entry_name in ['轨道-上', '轨道-下', '轨道-右']:
                    pass
                else:
                    _add_directed_edge(edges, i, j)
            elif _above(node_1, node_2):  # 1在2上边
                if node_2.entry.entry_name in ['轨道-上']:
                    pass
                elif node_1.entry.entry_name in ['轨道-左', '轨道-右', '轨道-上']:
                    pass
                else:
                    _add_directed_edge(edges, i, j)
            elif _under(node_1, node_2):  # 1在2下边
                if node_2.entry.entry_name in ['轨道-下']:
                    pass
                elif node_1.entry.entry_name in ['轨道-左', '轨道-右', '轨道-下']:
                    pass
                else:
                    _add_directed_edge(edges, i, j)

    return HollowZeroMap(nodes, current_idx, edges, check_time=check_time)


def _at_left(node_1: HollowZeroMapNode, node_2: HollowZeroMapNode) -> bool:
    """
    1在2左边
    :param node_1:
    :param node_2:
    :return:
    """
    min_width = min(node_1.pos.width,  node_2.pos.width) // 4
    return abs(node_1.pos.x2 - node_2.pos.x1) <= min_width and _is_same_row(node_1, node_2)


def _at_right(node_1: HollowZeroMapNode, node_2: HollowZeroMapNode) -> bool:
    """
    1在2右边
    :param node_1:
    :param node_2:
    :return:
    """
    min_width = min(node_1.pos.width,  node_2.pos.width) // 4
    return abs(node_1.pos.x1 - node_2.pos.x2) <= min_width and _is_same_row(node_1, node_2)


def _above(node_1: HollowZeroMapNode, node_2: HollowZeroMapNode) -> bool:
    """
    1在2上边
    :param node_1:
    :param node_2:
    :return:
    """
    min_height = min(node_1.pos.height,  node_2.pos.height) // 4
    return abs(node_1.pos.y2 - node_2.pos.y1) <= min_height and _is_same_col(node_1, node_2)


def _under(node_1: HollowZeroMapNode, node_2: HollowZeroMapNode) -> bool:
    """
    1在2上边
    :param node_1:
    :param node_2:
    :return:
    """
    min_height = min(node_1.pos.height,  node_2.pos.height) // 4
    return abs(node_1.pos.y1 - node_2.pos.y2) <= min_height and _is_same_col(node_1, node_2)


def _is_same_row(node_1: HollowZeroMapNode, node_2: HollowZeroMapNode) -> bool:
    min_height = min(node_1.pos.height,  node_2.pos.height) // 3
    y1_close = abs(node_1.pos.y1 - node_2.pos.y1) <= min_height
    y2_close = abs(node_1.pos.y2 - node_2.pos.y2) <= min_height
    return y1_close or y2_close


def _is_same_col(node_1: HollowZeroMapNode, node_2: HollowZeroMapNode) -> bool:
    min_width = min(node_1.pos.width,  node_2.pos.width) // 3
    x1_close = abs(node_1.pos.x1 - node_2.pos.x1) <= min_width
    x2_close = abs(node_1.pos.x2 - node_2.pos.x2) <= min_width
    return x1_close or x2_close


def _add_edge(edges: dict[int, List[int]], x: int, y: int) -> None:
    _add_directed_edge(edges, x, y)
    _add_directed_edge(edges, y, x)


def _add_directed_edge(edges: dict[int, List[int]], x: int, y: int) -> None:
    if x not in edges:
        edges[x] = [y]
    else:
        edges[x].append(y)


def is_same_map(map_1: HollowZeroMap, map_2: HollowZeroMap) -> bool:
    """
    判断两个地图是否同一个地图
    通常情况下，两个地图的差异是在一步移动之后产生的，因此大部分节点都应该一致
    当相同节点数量 >= 1/2 地图节点时，认为地图一致
    :param map_1: 地图1
    :param map_2: 地图2
    :return:
    """
    node_cnt_1 = len(map_1.nodes)
    node_cnt_2 = len(map_2.nodes)

    if node_cnt_1 == 0 and node_cnt_2 == 0:
        return True
    elif node_cnt_1 == 0 or node_cnt_2 == 0:
        return False

    same_node_cnt = 0
    for node_1 in map_1.nodes:
        for node_2 in map_2.nodes:
            if is_same_node(node_1, node_2):
                same_node_cnt += 1
                break

    # 极端情况下 是在3个格子的情况下移动 剩下2个格子
    # 如果移动后有在内存将格子更新为当前 则本次识别的2个格子的应该跟之前的一样 因此至少有50%格子一致
    # 必须要两个地图都有50%格子在另一张地图上 因为进入盲盒区域后 可能区域里只有少量格子 但跟外层的地图刚好重合
    return same_node_cnt >= node_cnt_1 * 0.5 and same_node_cnt >= node_cnt_2 * 0.5


def is_new_construction_section(old_map: HollowZeroMap, new_map: HollowZeroMap, target: HollowZeroMapNode) -> bool:
    """施工废墟末端商人或危机后重新展开多排地图，不能继续等待旧坐标。"""
    if not old_map.is_valid_map or not new_map.is_valid_map or target.entry.entry_name not in ('邦布商人', '危机'):
        return False
    ignored = {'未知', '空白已通行', '空白未通行'}
    old_nodes = [node for node in old_map.nodes if node.entry.entry_name not in ignored]
    new_nodes = [node for node in new_map.nodes if node.entry.entry_name not in ignored]
    if len(old_nodes) != 2 or len(new_nodes) < 6:
        return False
    source = old_map.nodes[old_map.current_idx].pos
    current = new_map.nodes[new_map.current_idx].pos
    # 两格尾段横向排列；新图从左侧重新展开，至少覆盖两排、四列和三种类型。
    return (target.pos.center.x > source.center.x
            and abs(target.pos.center.y - source.center.y) < source.height / 2
            and current.x2 < source.x1 and current.x2 < target.pos.x1
            and len({node.entry.entry_name for node in new_nodes}) >= 3
            and max(node.pos.center.x for node in new_nodes) - min(node.pos.center.x for node in new_nodes) > current.width * 3
            and max(node.pos.center.y for node in new_nodes) - min(node.pos.center.y for node in new_nodes) > current.height)


def is_arrived_after_camera_move(old_map: HollowZeroMap, new_map: HollowZeroMap, target: HollowZeroMapNode,
                                construction_tail: bool = False, old_screen: MatLike | None = None,
                                new_screen: MatLike | None = None) -> bool:
    """镜头平移后用周围格子的相对排列确认到达，同时排除仍在原地的视角。"""
    if not old_map.is_valid_map or not new_map.is_valid_map:
        return False
    current = new_map.nodes[new_map.current_idx].pos
    source = old_map.nodes[old_map.current_idx].pos
    if not (.75 <= target.pos.width / source.width <= 1.25
            and .75 <= target.pos.height / source.height <= 1.25):
        # 大电视的中心不等于进入后的头像落点；本判据只处理普通单格。
        return False
    ignored = {'当前', '未知', '空白已通行', '空白未通行'}
    new_named = [node.entry.entry_name for node in new_map.nodes if node.entry.entry_name not in ignored]
    evidence: list[tuple[int, int]] = []
    for origin in (target.pos, source):
        scale_x, scale_y = current.width / source.width, current.height / source.height
        matched: set[int] = set()
        matching, conflicting = 0, 0
        for old_node in old_map.nodes:
            if old_node is target or old_node.entry.entry_name in ignored:
                continue
            x = current.center.x + (old_node.pos.center.x - origin.center.x) * scale_x
            y = current.center.y + (old_node.pos.center.y - origin.center.y) * scale_y
            for index, new_node in enumerate(new_map.nodes):
                if index in matched or new_node.entry.entry_name in ignored:
                    continue
                if new_node.pos.x1 <= x < new_node.pos.x2 and new_node.pos.y1 <= y < new_node.pos.y2:
                    matched.add(index)
                    # 施工废墟接应增援后，同列另一增援格会变为硬币；它不能作为位置证据。
                    if (construction_tail
                            and target.entry.entry_name == '呼叫增援'
                            and old_node.entry.entry_name == '呼叫增援'
                            and abs(old_node.pos.center.x - target.pos.center.x) < target.pos.width / 2
                            and target.pos.height / 2 < abs(old_node.pos.center.y - target.pos.center.y) < target.pos.height * 1.5
                            and new_node.entry.entry_name == '齿轮硬币箱'):
                        break
                    if old_node.entry.entry_name == new_node.entry.entry_name:
                        matching += 1
                    else:
                        conflicting += 1
                    break
        evidence.append((matching, conflicting))
    arrived, stayed = evidence
    if arrived[0] >= 2 and arrived[1] == 0 and arrived[0] > stayed[0] and stayed[1] >= 2:
        return True
    old_active = [node for index, node in enumerate(old_map.nodes)
                  if index == old_map.current_idx or node is target or node.entry.entry_name not in ignored]
    new_active = [node for index, node in enumerate(new_map.nodes)
                  if index == new_map.current_idx or node.entry.entry_name not in ignored]
    if (construction_tail and len(old_active) >= 3 and len(new_active) == len(old_active) - 1
            and len(new_named) >= 1
            and all(abs(source.center.y - node.pos.center.y) < source.height / 4 for node in old_active)
            and all(abs(current.center.y - node.pos.center.y) < current.height / 4 for node in new_active)
            and old_screen is not None and new_screen is not None):
        landmarks = sorted((node for node in old_map.nodes if node.pos.center.x > target.pos.center.x
                            and node.entry.entry_name not in ignored
                            and node.entry.entry_name != target.entry.entry_name), key=lambda node: node.pos.center.x)
        if not landmarks:
            return False
        old_landmark = landmarks[0]
        new_landmarks = [node for node in new_map.nodes if node.entry.entry_name == old_landmark.entry.entry_name]
        if len(new_landmarks) != 1:
            return False
        new_landmark = new_landmarks[0]
        old_pos, new_pos = old_landmark.pos, new_landmark.pos
        candidates = [target] + [node for node in old_active
                                 if target.pos.center.x < node.pos.center.x < old_pos.center.x]
        samples = [(old_screen, node.pos) for node in candidates] + [(old_screen, old_pos), (new_screen, new_pos)]
        histograms: list[MatLike] = []
        for image, rect in samples:
            # 比较格子内有颜色的图案，排除灰色电视边框及明暗动画的影响。
            inset_x, inset_y = int(rect.width * .1), int(rect.height * .1)
            crop = image[rect.y1 + inset_y:rect.y2 - inset_y, rect.x1 + inset_x:rect.x2 - inset_x]
            if crop.size == 0:
                return False
            hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
            mask = cv2.inRange(hsv, (0, 70, 45), (179, 255, 255))
            if cv2.countNonZero(mask) < mask.size * .1:
                return False
            histogram = cv2.calcHist([hsv], [0, 1], mask, [30, 32], [0, 180, 0, 256])
            histograms.append(cv2.normalize(histogram, None, norm_type=cv2.NORM_L1))
        # 排除中间格是漏识的第二个同类地标；已识别的不同类型允许近色，但不能与地标高度相似。
        if (any(cv2.compareHist(histogram, histograms[-2], cv2.HISTCMP_INTERSECT)
                >= (.35 if node.entry.entry_name in ignored else .75)
                for node, histogram in zip(candidates, histograms[:-2], strict=True))
                or cv2.compareHist(histograms[-2], histograms[-1], cv2.HISTCMP_INTERSECT) < .75):
            return False
        # 移除最左格时头像右移、地标左移；保留四分之一格幅度，容纳稳定检测已允许的 4 像素框误差。
        return (arrived[0] >= 1 and arrived[1] == 0 and arrived[0] > stayed[0]
                and source.center.x < target.pos.center.x < old_pos.center.x
                and current.center.x - source.center.x > max(4, source.width / 4 - 4)
                and old_pos.center.x - new_pos.center.x > max(4, source.width / 4 - 4))
    return False


def _has_unchanged_landmarks(old_map: HollowZeroMap, new_map: HollowZeroMap) -> bool:
    """按原头像对齐后，至少两个无冲突地标说明仍可能停留原图，不能仅靠出口漏检确认换图。"""
    source = old_map.nodes[old_map.current_idx].pos
    current = new_map.nodes[new_map.current_idx].pos
    ignored = {'当前', '未知', '空白已通行', '空白未通行'}
    matched: set[int] = set()
    for old in old_map.nodes:
        if old.entry.entry_name in ignored:
            continue
        x = current.center.x + (old.pos.center.x - source.center.x) * current.width / source.width
        y = current.center.y + (old.pos.center.y - source.center.y) * current.height / source.height
        for index, new in enumerate(new_map.nodes):
            if index in matched or new.entry.entry_name in ignored:
                continue
            if new.pos.x1 <= x < new.pos.x2 and new.pos.y1 <= y < new.pos.y2:
                if old.entry.entry_name != new.entry.entry_name:
                    return False
                matched.add(index)
                break
    return len(matched) >= 2


def is_returned_from_random_zone(origin: HollowZeroMap, current_map: HollowZeroMap, entrance: HollowZeroMapNode,
                                previous_map: HollowZeroMap) -> bool:
    """以进入盲盒前实际观察的主图地标确认返回，不靠区域内格子与主图碰巧重叠。"""
    if not origin.is_valid_map or not current_map.is_valid_map:
        return False
    if any(node.entry.entry_name == '不宜久留' for node in current_map.nodes):
        return False
    if _has_unchanged_landmarks(previous_map, current_map):
        return False
    ignored = {'当前', '未知', '空白已通行', '空白未通行'}
    current = current_map.nodes[current_map.current_idx].pos
    source = origin.nodes[origin.current_idx].pos
    scale_x, scale_y = current.width / source.width, current.height / source.height
    matched: set[int] = set()
    for old in origin.nodes:
        if old is entrance or old.entry.entry_name in ignored:
            continue
        x = current.center.x + (old.pos.center.x - entrance.pos.center.x) * scale_x
        y = current.center.y + (old.pos.center.y - entrance.pos.center.y) * scale_y
        for index, new in enumerate(current_map.nodes):
            if index in matched or new.entry.entry_name in ignored:
                continue
            if new.pos.x1 <= x < new.pos.x2 and new.pos.y1 <= y < new.pos.y2:
                if old.entry.entry_name != new.entry.entry_name:
                    return False
                matched.add(index)
                break
    if len(matched) >= 2:
        return True
    # 主图末端仅剩一个地标时，还需确认它在区域内没有出现，且多排小图已收缩成两格。
    origin_named = [node for node in origin.nodes if node is not entrance and node.entry.entry_name not in ignored]
    previous_names = {node.entry.entry_name for node in previous_map.nodes}
    return (len(matched) == 1 and len(current_map.nodes) == 2 and len(origin_named) == 1
            and origin_named[0].entry.entry_name not in previous_names
            and len(previous_map.nodes) >= 4 and '不宜久留' in previous_names
            and abs(current.center.y - current_map.nodes[next(iter(matched))].pos.center.y) < current.height / 4
            and max(node.pos.center.y for node in previous_map.nodes) - min(node.pos.center.y for node in previous_map.nodes)
            > previous_map.nodes[previous_map.current_idx].pos.height)


def is_new_map_after_teleport(old_map: HollowZeroMap, new_map: HollowZeroMap, target: HollowZeroMapNode) -> bool:
    """用已识别格子的拓扑变化确认换图，排除漏检、缩放以及只走到传送格。"""
    if not old_map.is_valid_map or not new_map.is_valid_map:
        return False
    current = new_map.nodes[new_map.current_idx].pos
    ignored = {'当前', '未知', '空白已通行', '空白未通行'}
    if target.entry.entry_name == '盲盒区域':
        old_names = {node.entry.entry_name for node in old_map.nodes}
        new_names = {node.entry.entry_name for node in new_map.nodes}
        exits = [node for node in new_map.nodes if node.entry.entry_name == '不宜久留']
        middle = [node for index, node in enumerate(new_map.nodes)
                  if index != new_map.current_idx and node.entry.entry_name != '不宜久留']
        # 五格十字盲盒的按钮可能漏识；用上方头像、下方出口及中间三格确认已知布局。
        cross = (len(new_map.nodes) == 5 and len(exits) == 1 and len(middle) == 3
                 and abs(current.center.x - exits[0].pos.center.x) < current.width / 4
                 and all(current.y2 <= node.pos.y1 + current.height / 4
                         and node.pos.y2 <= exits[0].pos.y1 + current.height / 4 for node in middle)
                 and max(node.pos.center.y for node in middle) - min(node.pos.center.y for node in middle) < current.height / 4
                 and sum(abs(node.pos.center.x - current.center.x) < current.width / 4 for node in middle) == 1
                 and min(node.pos.x2 for node in middle) < current.x1
                 and max(node.pos.x1 for node in middle) > current.x2)
        # 盲盒小图可能只与旧图重叠一格；新出现的出口和多排事件格共同证明进入独立区域。
        if ('不宜久留' not in old_names and not _has_unchanged_landmarks(old_map, new_map)
                and len(exits) == 1
                and (cross or (len(new_map.nodes) >= 6 and len(new_names - ignored - {'不宜久留'}) >= 2))
                and max(node.pos.center.x for node in new_map.nodes) - min(node.pos.center.x for node in new_map.nodes) > current.width
                and max(node.pos.center.y for node in new_map.nodes) - min(node.pos.center.y for node in new_map.nodes) > current.height):
            return True
    if target.entry.entry_name == '不宜久留':
        source = old_map.nodes[old_map.current_idx].pos
        named = [node for node in new_map.nodes if node.entry.entry_name not in ignored]
        # 已走空的盲盒环没有地标可比较：仅接受从最右侧出口回到多排主图左端。
        if (len(old_map.nodes) >= 8
                and all(node.entry.entry_name in ('当前', '不宜久留', '空白已通行') for node in old_map.nodes)
                and all(node.pos.center.x <= min(source.x2, target.pos.x2) for node in old_map.nodes)
                and abs(source.center.x - target.pos.center.x) < source.width / 2
                and current.x2 < min(source.x1, target.pos.x1)
                and len(named) >= 5 and len({node.entry.entry_name for node in named}) >= 3
                and all(node.entry.entry_name != '不宜久留' for node in new_map.nodes)
                and all(node.pos.center.x >= current.x1 for node in new_map.nodes)
                and max(node.pos.center.x for node in named) - current.center.x > current.width * 2
                and max(node.pos.center.y for node in named) - min(node.pos.center.y for node in named) > current.height):
            return True
    conflicting_new: set[int] = set()
    sparse_evidence = False
    source = old_map.nodes[old_map.current_idx].pos
    for origin in (old_map.nodes[old_map.current_idx].pos, target.pos):
        # 两种视角共用头像尺度；目标格检测框大小不同不能凭空产生换图证据。
        scale_x, scale_y = current.width / source.width, current.height / source.height
        matching, conflicting = 0, 0
        matched_new: set[int] = set()
        for old_node in old_map.nodes:
            if old_node.entry.entry_name in ignored:
                continue
            x = current.center.x + (old_node.pos.center.x - origin.center.x) * scale_x
            y = current.center.y + (old_node.pos.center.y - origin.center.y) * scale_y
            for index, new_node in enumerate(new_map.nodes):
                if index in matched_new or new_node.entry.entry_name in ignored:
                    continue
                if new_node.pos.x1 <= x < new_node.pos.x2 and new_node.pos.y1 <= y < new_node.pos.y2:
                    # 大电视只能作为一个独立证据，不能重复覆盖多个旧格来凑冲突数。
                    matched_new.add(index)
                    if old_node.entry.entry_name == new_node.entry.entry_name:
                        matching += 1
                    else:
                        conflicting += 1
                        conflicting_new.add(index)
                    break
        # 每种旧图视角都必须被明确冲突排除，漏检不算证据；边缘出生点可能只重叠一格。
        if conflicting <= matching:
            return False
        sparse_evidence |= conflicting < 2
    # 两种对齐合计仍需两个独立的新格，不能用同一大电视重复证明换图。
    if len(conflicting_new) < 2:
        return False
    if sparse_evidence:
        # 边缘重叠较少时还需头像明显换位；原地误分类或仅站上传送格不能靠单格冲突通过。
        return all(current.x2 <= origin.x1 or current.x1 >= origin.x2
                   or current.y2 <= origin.y1 or current.y1 >= origin.y2
                   for origin in (old_map.nodes[old_map.current_idx].pos, target.pos))
    return True


def merge_map(ctx: ZContext, map_list: List[HollowZeroMap]):
    """
    将多个地图合并成一个
    """
    nodes: List[HollowZeroMapNode] = []
    max_check_time: Optional[float] = None

    # 每个地图的节点取出来后去重合并
    for m in map_list:
        for node in m.nodes:
            to_merge: Optional[HollowZeroMapNode] = None
            for existed in nodes:
                if is_same_node_pos(node, existed):
                    to_merge = existed
                    break

            if to_merge is not None:
                if to_merge.entry.is_base:  # 旧的是底座 那么将新的类型赋值上去
                    to_merge.entry = node.entry
                elif node.entry.is_base:  # 旧的是格子类型 新的是底座 将底座范围赋值上去
                    to_merge.pos = node.pos
                elif to_merge.entry.entry_name == '未知' and node.entry.entry_name != '未知':  # 新旧都是格子类型 旧的是未知 将新的类型赋值上去
                    to_merge.entry = node.entry
                elif to_merge.entry.entry_name != '未知' and node.entry.entry_name == '未知':  # 新旧都是格子类型 新的是未知 保持不变
                    pass
                elif to_merge.confidence > 0.95 and node.confidence > 0.95:
                    if to_merge.check_time < node.check_time:  # 两者置信度都很高 保留时间最新的结果
                        to_merge.entry = node.entry
                elif to_merge.confidence < node.confidence:  # 新旧都是格子类型 旧的识别置信度低 将新的类型赋值上去
                    to_merge.entry = node.entry
                elif to_merge.check_time < node.check_time:  # 新旧都是格子类型 新的识别时间更晚 将新的类型赋值上去
                    to_merge.entry = node.entry
            else:
                nodes.append(node)

        if max_check_time is None or m.check_time > max_check_time:
            max_check_time = m.check_time

    return construct_map_from_nodes(ctx, nodes, max_check_time)


def is_same_node_pos(x: HollowZeroMapNode, y: HollowZeroMapNode) -> bool:
    """
    判断两个节点的坐标是否一致
    """
    if x is None or y is None:
        return False
    min_dis = min(x.pos.height, x.pos.width, y.pos.height, y.pos.width) // 2
    return cal_utils.distance_between(x.pos.center, y.pos.center) < min_dis


def is_same_node(x: HollowZeroMapNode, y: HollowZeroMapNode) -> bool:
    """
    判断两个节点是否同一个节点
    """
    if x is None or y is None:
        return False
    return x.entry.entry_name == y.entry.entry_name and is_same_node_pos(x, y)


def get_node_index(current_map: HollowZeroMap, node: HollowZeroMapNode) -> int:
    """
    获取某个节点 在地图上的下标
    @param current_map: 地图
    @param node: 节点
    @return: 下标
    """
    for i in range(len(current_map.nodes)):
        if is_same_node(current_map.nodes[i], node):
            return i
