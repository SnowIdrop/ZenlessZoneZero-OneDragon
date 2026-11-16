import time
from typing import ClassVar, List, Optional, Type

from cv2.typing import MatLike

from one_dragon.base.geometry.point import Point
from one_dragon.base.geometry.rectangle import Rect
from one_dragon.base.operation.application import application_const
from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils import cal_utils
from one_dragon.utils.i18_utils import gt
from one_dragon.utils.log_utils import log
from zzz_od.application.hollow_zero.withered_domain.withered_domain_config import (
    HollowZeroExtraExitEnum,
    HollowZeroExtraTask,
    WitheredDomainConfig,
)
from zzz_od.application.hollow_zero.withered_domain.withered_domain_run_record import (
    WitheredDomainRunRecord,
)
from zzz_od.context.zzz_context import ZContext
from zzz_od.hollow_zero.event import hollow_event_utils
from zzz_od.hollow_zero.event.bamboo_merchant import BambooMerchant
from zzz_od.hollow_zero.event.call_for_support import CallForSupport
from zzz_od.hollow_zero.event.choose_resonium import ChooseResonium
from zzz_od.hollow_zero.event.confirm_resonium import ConfirmResonium
from zzz_od.hollow_zero.event.critical_stage import CriticalStage
from zzz_od.hollow_zero.event.door_battle import DoorBattle
from zzz_od.hollow_zero.event.drop_resonium import DropResonium, DropResonium2
from zzz_od.hollow_zero.event.full_in_bag import FullInBag
from zzz_od.hollow_zero.event.leave_random_zone import LeaveRandomZone
from zzz_od.hollow_zero.event.normal_event_handler import NormalEventHandler
from zzz_od.hollow_zero.event.old_capital import OldCapital
from zzz_od.hollow_zero.event.remove_corruption import RemoveCorruption
from zzz_od.hollow_zero.event.swift_supply import SwiftSupply
from zzz_od.hollow_zero.event.switch_resonium import SwitchResonium
from zzz_od.hollow_zero.event.upgrade_resonium import UpgradeResonium
from zzz_od.hollow_zero.game_data.hollow_zero_event import HollowZeroSpecialEvent
from zzz_od.hollow_zero.hollow_battle import HollowBattle
from zzz_od.hollow_zero.hollow_exit_by_menu import HollowExitByMenu
from zzz_od.hollow_zero.hollow_map import hollow_map_utils, hollow_pathfinding
from zzz_od.hollow_zero.hollow_map.hollow_zero_map import (
    HollowZeroMap,
    HollowZeroMapNode,
)
from zzz_od.operation.zzz_operation import ZOperation


class HollowRunner(ZOperation):

    STATUS_LEAVE: ClassVar[str] = '离开空洞'

    def __init__(self, ctx: ZContext):
        ZOperation.__init__(
            self, ctx,
            op_name=gt('空洞操作器', 'game')
        )

        self.config: WitheredDomainConfig = self.ctx.run_context.get_config(
            app_id=self.ctx.withered_domain.app_id,
            instance_idx=self.ctx.current_instance_idx,
            group_id=application_const.DEFAULT_GROUP_ID,
        )
        self.run_record: WitheredDomainRunRecord = self.ctx.run_context.get_run_record(
            instance_idx=self.ctx.current_instance_idx,
            app_id=self.ctx.withered_domain.app_id,
        )

        self._special_event_handlers: dict[str, Type] = {
            HollowZeroSpecialEvent.CALL_FOR_SUPPORT.value.event_name: CallForSupport,

            HollowZeroSpecialEvent.RESONIUM_STORE_0.value.event_name: BambooMerchant,
            HollowZeroSpecialEvent.RESONIUM_STORE_1.value.event_name: BambooMerchant,
            HollowZeroSpecialEvent.RESONIUM_STORE_2.value.event_name: BambooMerchant,
            HollowZeroSpecialEvent.RESONIUM_STORE_3.value.event_name: BambooMerchant,
            HollowZeroSpecialEvent.RESONIUM_STORE_4.value.event_name: BambooMerchant,
            # HollowZeroSpecialEvent.RESONIUM_STORE_5.value.event_name: BambooMerchant,

            HollowZeroSpecialEvent.RESONIUM_CHOOSE.value.event_name: ChooseResonium,
            HollowZeroSpecialEvent.RESONIUM_CONFIRM_1.value.event_name: ConfirmResonium,
            HollowZeroSpecialEvent.RESONIUM_CONFIRM_2.value.event_name: ConfirmResonium,
            HollowZeroSpecialEvent.RESONIUM_UPGRADE.value.event_name: UpgradeResonium,
            HollowZeroSpecialEvent.RESONIUM_DROP.value.event_name: DropResonium,
            HollowZeroSpecialEvent.RESONIUM_DROP_2.value.event_name: DropResonium2,
            HollowZeroSpecialEvent.RESONIUM_SWITCH.value.event_name: SwitchResonium,
            HollowZeroSpecialEvent.SWIFT_SUPPLY_LIFE.value.event_name: SwiftSupply,
            HollowZeroSpecialEvent.SWIFT_SUPPLY_COIN.value.event_name: SwiftSupply,
            HollowZeroSpecialEvent.SWIFT_SUPPLY_PRESS.value.event_name: SwiftSupply,

            HollowZeroSpecialEvent.CORRUPTION_REMOVE.value.event_name: RemoveCorruption,

            HollowZeroSpecialEvent.CRITICAL_STAGE_ENTRY.value.event_name: CriticalStage,
            HollowZeroSpecialEvent.CRITICAL_STAGE_ENTRY_2.value.event_name: CriticalStage,

            HollowZeroSpecialEvent.IN_BATTLE.value.event_name: HollowBattle,
            HollowZeroSpecialEvent.FULL_IN_BAG.value.event_name: FullInBag,
            HollowZeroSpecialEvent.OLD_CAPITAL.value.event_name: OldCapital,

            # HollowZeroSpecialEvent.DOOR_BATTLE_ENTRY.value.event_name: DoorBattle,
            # HollowZeroSpecialEvent.NEED_INTERACT.value.event_name: HollowInteract,
        }

        # 部分格子有一个选项作为入口
        self._entry_event_handlers: dict[str, Type] = {
            '邦布商人': BambooMerchant,
            '守门人': CriticalStage,
            '门扉禁闭-善战': DoorBattle,
            '门扉禁闭-侵蚀': DoorBattle,
            '不宜久留': LeaveRandomZone
        }
        self._entry_events: dict[str, List[str]] = {
            '邦布商人': ['进入商店'],
        }

        self._last_save_image_time: float = 0
        self._last_move_time: float = 0  # 上一次移动的时间
        self._pending_gamepad_move: tuple[HollowZeroMap, HollowZeroMapNode] | None = None
        self._gamepad_move_screen: MatLike | None = None
        self._gamepad_random_zone_origin: tuple[HollowZeroMap, HollowZeroMapNode] | None = None
        self._gamepad_waypoint: tuple[str, Rect] | None = None
        self._gamepad_obstacle_hits: int = 0
        self._gamepad_move_checks: int = 0
        self._gamepad_map_candidate: tuple[HollowZeroMap, HollowZeroMap] | None = None

        self._handled_events: set[str] = set()  # 当前已处理过的事件 移动后清空
        self._gamepad_prompt: tuple[str, float] | None = None

    def handle_pause(self) -> None:
        """暂停中断地图稳定性观察，恢复后重新取证。"""
        self._gamepad_map_candidate = None
        self._gamepad_prompt = None
        self._gamepad_waypoint = None

    @operation_node(name='画面识别', is_start_node=True, node_max_retry_times=60)
    def check_screen(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode and all(
            self.round_by_find_area(self.last_screenshot, '零号空洞-事件', name).is_success
            for name in ('手柄-通关标题', '手柄-通关完成')
        ):
            return self.round_success('通关-完成')
        prompt = None
        if self.ctx.controller.background_mode and all(
            self.round_by_find_area(self.last_screenshot, '零号空洞-事件', name).is_success
            for name in ('手柄-插件获得', '手柄-插件确定', '手柄-消息选择')
        ):
            prompt = '确认获得邦布插件'
        if self.ctx.controller.background_mode and all(
            self.round_by_find_area(self.last_screenshot, '零号空洞-事件', name).is_success
            for name in ('手柄-消息确认', '手柄-消息选择')
        ):
            prompt = '确认事件消息'
        if self.ctx.controller.background_mode and all(
            self.round_by_find_area(self.last_screenshot, '零号空洞-事件', name).is_success
            for name in ('背包', '手柄-事件继续')
        ):
            prompt = '继续事件对话'
        if prompt is not None:
            self._gamepad_map_candidate = None
            self._gamepad_waypoint = None
            if self._gamepad_prompt is None or self._gamepad_prompt[0] != prompt:
                self._gamepad_prompt = (prompt, time.monotonic())
            elif time.monotonic() - self._gamepad_prompt[1] > 10:
                return self.round_fail(f'{prompt}持续未消失，停止重复确认')
            self.ctx.controller.gamepad_ui_press('confirm')
            return self.round_wait(prompt, wait=.5)
        self._gamepad_prompt = None
        result = hollow_event_utils.check_screen(self.ctx, self.last_screenshot, self._handled_events)
        if (self.ctx.controller.background_mode
                and hollow_event_utils.is_challenge_result(self.ctx, self.last_screenshot)):
            # 停止后从战斗结算续跑时，仍交给战斗流程验证确认按钮及下一层。
            result = HollowZeroSpecialEvent.IN_BATTLE.value.event_name
        if (self.ctx.controller.background_mode
                and result == HollowZeroSpecialEvent.DOOR_BATTLE_ENTRY.value.event_name
                and self._pending_gamepad_move is not None
                and self._pending_gamepad_move[1].entry.entry_name in ('门扉禁闭-善战', '门扉禁闭-侵蚀')):
            self._gamepad_map_candidate = None
            # 方向键先触发邻格门的选项，开门不会移动头像；完成交互后重新规划实际入格。
            door_result = DoorBattle(self.ctx).execute()
            if not door_result.success:
                return self.round_fail(door_result.status)
            destination = self._pending_gamepad_move[1].pos
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                screen = self.screenshot()
                current_map = self.ctx.withered_domain.map_service.cal_map_by_screen(screen, self.last_screenshot_time)
                if current_map is not None and any(
                    node.entry.entry_name == '开启的门' and node.check_time == self.last_screenshot_time
                    and destination.x1 <= node.pos.center.x < destination.x2
                    and destination.y1 <= node.pos.center.y < destination.y2 for node in current_map.nodes
                ):
                    break
                time.sleep(.1)
            else:
                return self.round_fail('未观察到目标门开启')
            self._pending_gamepad_move = None
            return self.round_wait('已处理邻格开门选项', wait=.5)
        if result is not None and result not in [
            HollowZeroSpecialEvent.HOLLOW_INSIDE.value.event_name,  # 空洞内部比较特殊 仅为识别使用 不做响应处理
            HollowZeroSpecialEvent.RESONIUM_STORE_5.value.event_name,  # 商人格子不会消失 为了防止循环进入商店 仅在移动格子时候触发进入商店 平时出现这个选项不做点击
            HollowZeroSpecialEvent.DOOR_BATTLE_ENTRY.value.event_name,  # 这扇门在第一次过去的时候就会开 如果没开到 说明上场战斗没有S 开不了 就不继续了
        ]:
            self._gamepad_map_candidate = None
            self._gamepad_waypoint = None
            level_info = self.ctx.withered_domain.level_info
            previous_level = level_info.level if level_info is not None else None
            event_result = self._handle_event(self.last_screenshot, result)
            level_info = self.ctx.withered_domain.level_info
            if level_info is not None and level_info.level != previous_level:
                # 守门人交互可能先于入格确认；已核实换层后，旧层的待到达格失效。
                self._pending_gamepad_move = None
                self._gamepad_random_zone_origin = None
            return event_result

        if result in [
            HollowZeroSpecialEvent.HOLLOW_INSIDE.value.event_name,  # 当前有显示背包 可以尝试识别地图
            HollowZeroSpecialEvent.RESONIUM_STORE_5.value.event_name,  # 商人格子也需要寻路
            HollowZeroSpecialEvent.DOOR_BATTLE_ENTRY.value.event_name,  # 门扉禁闭-善战 开不了门 就移动去其他地方
        ]:
            if self.ctx.controller.background_mode:
                # 手柄只能走当前可见的相邻格；合并缓存会保留动画中误识别的安全区等旧格。
                current_map = self.ctx.withered_domain.map_service.cal_current_map_by_screen(self.last_screenshot, self.last_screenshot_time)
            else:
                current_map = self.ctx.withered_domain.map_service.cal_map_by_screen(self.last_screenshot, self.last_screenshot_time)
            if current_map is not None:
                result = self.try_move_by_map(self.last_screenshot, self.last_screenshot_time, current_map)
                if result is not None:
                    return result
            else:
                self._gamepad_map_candidate = None
            # 识别不到地图 说明可能是空洞里有需要确认的对话框 随便点击一下吧对话框取消掉
            if current_map is None and not self.ctx.controller.background_mode:
                self.round_by_click_area('零号空洞-事件', '空白')
        elif not self.ctx.controller.background_mode:
            # 未知的情况 点击一下继续
            self.round_by_click_area('零号空洞-事件', '空白')

        self._gamepad_map_candidate = None

        return self.round_retry('未能识别当前画面', wait=1)

    def _handle_event(self, screen: MatLike, event_name: str) -> OperationRoundResult:
        """
        识别到事件时 进行处理
        :param event_name:
        :return:
        """
        normal_event = self.ctx.withered_domain.data_service.get_normal_event_by_name(event_name=event_name)
        any_match = False
        if normal_event is not None:
            any_match = True
            log.info('匹配普通事件 [%s]', event_name)
            if normal_event.is_entry_opt:
                self._handled_events.add(event_name)
            op = NormalEventHandler(self.ctx, normal_event)
            op_result = op.execute()
            if op_result.success:  # 失败的时候继续尝试特殊事件 防止错误匹配到普通事件上
                return self.round_wait()

        if event_name in self._special_event_handlers:
            any_match = True
            log.info('匹配特殊事件 [%s]', event_name)
            special_event = hollow_event_utils.get_special_event_by_name(event_name)
            if special_event.is_entry_opt:
                self._handled_events.add(event_name)

            op: ZOperation = self._special_event_handlers[event_name](self.ctx)
            op_result = op.execute()
            if op_result.success:
                return self.round_wait()

        if event_name == HollowZeroSpecialEvent.MISSION_COMPLETE.value.event_name:
            return self.round_success(status='通关-完成')

        if any_match:
            return self.round_retry('事件处理失败', wait=1)
        else:
            return self.round_retry('当前事件未有对应指令', wait=1)

    def _is_gamepad_map_stable(self, current_map: HollowZeroMap, screen_time: float) -> bool:
        """等待头像格的位置和尺寸稳定，避免在地图缩放期间发送无效输入。"""
        if not current_map.is_valid_map:
            self._gamepad_map_candidate = None
            return False
        candidate = self._gamepad_map_candidate
        current_pos = current_map.nodes[current_map.current_idx].pos
        previous_map, first_map = candidate if candidate is not None else (None, current_map)
        first_pos = first_map.nodes[first_map.current_idx].pos
        sparse_changed = (len(current_map.nodes) != len(first_map.nodes)
                          and 2 in (len(current_map.nodes), len(first_map.nodes)))
        if len(current_map.nodes) == len(first_map.nodes) == 2:
            # 三格尾段缩成两格后，还需观察末端地标稳定，不能忽略类型或尺寸跳变。
            old_nodes = sorted(first_map.nodes, key=lambda node: node.pos.center.x)
            new_nodes = sorted(current_map.nodes, key=lambda node: node.pos.center.x)
            sparse_changed = any(
                old.entry.entry_name != new.entry.entry_name
                or any(abs(a - b) > 4 for a, b in zip(
                    (old.pos.x1, old.pos.y1, old.pos.x2, old.pos.y2),
                    (new.pos.x1, new.pos.y1, new.pos.x2, new.pos.y2), strict=True))
                for old, new in zip(old_nodes, new_nodes, strict=True))
        if (previous_map is None or any(abs(a - b) > 4 for a, b in zip(
                (current_pos.x1, current_pos.y1, current_pos.x2, current_pos.y2),
                (first_pos.x1, first_pos.y1, first_pos.x2, first_pos.y2), strict=True))
                or sparse_changed or not 0 < screen_time - previous_map.check_time <= 1):
            self._gamepad_map_candidate = (current_map, current_map)
            return False
        self._gamepad_map_candidate = (current_map, first_map)
        return screen_time - first_map.check_time >= .5

    def try_move_by_map(self, screen: MatLike, screen_time: float, current_map: HollowZeroMap) -> Optional[OperationRoundResult]:
        """
        识别到地图后 尝试自动寻路并移动
        :param screen: 游戏画面
        :param screen_time: 截图时间
        :param current_map: 分析得到的地图
        :return:
        """
        if self.ctx.controller.background_mode and self._pending_gamepad_move is not None:
            previous_map, moved_node = self._pending_gamepad_move
            current_node = current_map.nodes[current_map.current_idx] if current_map.is_valid_map else None
            # 合并地图可能保留旧的“当前”节点，只有本帧识别到的当前位置能确认移动。
            if current_node is None or current_node.check_time != screen_time:
                self._gamepad_map_candidate = None
                # 事件展开时电视地图仍可见，但当前位置被覆盖；沿用画面识别的重试上限。
                return self.round_retry('未能识别当前电视位置', wait=1)
            if (moved_node.entry.entry_name in ('邦布商人', '危机')
                    and self.ctx.withered_domain.level_info.mission_type_name == '施工废墟'
                    and hollow_map_utils.is_new_construction_section(previous_map, current_map, moved_node)):
                if not self._is_gamepad_map_stable(current_map, screen_time):
                    return self.round_retry('等待施工废墟新区域稳定', wait=.25)
                self.ctx.withered_domain.reset_current_map()
                self._pending_gamepad_move = None
                self._gamepad_waypoint = None
                self._gamepad_map_candidate = None
                self._handled_events.clear()
                return self.round_wait('已确认施工废墟新区域')
            if moved_node.entry.is_tp:
                # 缺格或缩放也会使两图无法匹配；需在稳定画面中确认不同的格子排列。
                if not self._is_gamepad_map_stable(current_map, screen_time):
                    return self.round_retry('等待传送地图稳定', wait=.25)
                changed = hollow_map_utils.is_new_map_after_teleport(previous_map, current_map, moved_node)
                if moved_node.entry.entry_name == '不宜久留' and self._gamepad_random_zone_origin is not None:
                    origin, entrance = self._gamepad_random_zone_origin
                    changed = changed or hollow_map_utils.is_returned_from_random_zone(origin, current_map, entrance, previous_map)
                # 优先保留换图证据；没有换图证据时，盲盒也可能直接在主图结算。
                opened_here = (not changed and moved_node.entry.entry_name == '盲盒区域'
                               and not any(node.entry.entry_name == '不宜久留' for node in current_map.nodes)
                               and hollow_map_utils.is_arrived_after_camera_move(
                                   previous_map, current_map, moved_node,
                                   construction_tail=self.ctx.withered_domain.level_info.mission_type_name == '施工废墟',
                                   old_screen=self._gamepad_move_screen, new_screen=screen))
                if not changed and not opened_here:
                    return self.round_retry('等待传送后的新地图', wait=1)
                if moved_node.entry.entry_name == '盲盒区域':
                    self._gamepad_random_zone_origin = None if opened_here else (previous_map, moved_node)
                elif moved_node.entry.entry_name == '不宜久留':
                    self._gamepad_random_zone_origin = None
                self._pending_gamepad_move = None
                self._gamepad_map_candidate = None
                self._gamepad_waypoint = None
                self.ctx.withered_domain.update_context_after_move(previous_map, moved_node, update_current=False, same_map=opened_here)
                self._handled_events.clear()
                return self.round_wait('已确认盲盒在原图结算' if opened_here else '已确认传送后的新地图')
            destination_node = hollow_pathfinding.get_rail_exit(previous_map, moved_node)
            if destination_node is None:
                return self.round_fail('轨道出口未唯一确定')
            destination = destination_node.pos
            current_position = current_node.pos.center
            arrived = (destination.x1 <= current_position.x < destination.x2
                       and destination.y1 <= current_position.y < destination.y2)
            if not arrived:
                # 施工废墟移除旧排后会重置镜头；用周围格子核实位置，不能重复发移动键。
                camera_stable = self._is_gamepad_map_stable(current_map, screen_time)
                construction_tail = self.ctx.withered_domain.level_info.mission_type_name == '施工废墟'
                arrived = hollow_map_utils.is_arrived_after_camera_move(
                    previous_map, current_map, destination_node,
                    construction_tail=construction_tail,
                    old_screen=self._gamepad_move_screen if construction_tail else None, new_screen=screen)
                if arrived and not camera_stable:
                    return self.round_retry('等待移动后的镜头稳定', wait=.25)
                if arrived:
                    # 镜头变化后旧路标矩形可能被另一同类格占据，必须重新规划。
                    self._gamepad_waypoint = None
            if not arrived:
                self._gamepad_move_checks += 1
                if (moved_node.entry.entry_name == '残破的障碍物'
                        and self._gamepad_move_checks >= 3):
                    source = previous_map.nodes[previous_map.current_idx].pos
                    target_nodes = [node for node in current_map.nodes
                                    if destination.x1 <= node.pos.center.x < destination.x2
                                    and destination.y1 <= node.pos.center.y < destination.y2]
                    if (len(target_nodes) == 1 and source.x1 <= current_position.x < source.x2
                            and source.y1 <= current_position.y < source.y2):
                        revealed = target_nodes[0]
                        if (revealed.entry.entry_name not in ('残破的障碍物', '未知', '当前')
                                and revealed.entry.can_go):
                            # 破墙可能露出物资或事件；按新地图重新规划，不能当成已经进入该格。
                            self._pending_gamepad_move = None
                            self._gamepad_map_candidate = None
                            return self.round_wait('障碍物已破开，重新选择目标')
                        # 障碍物需要多次撞击；只在原地且目标仍可见时重试，不把撞击记为入格。
                        if (revealed.entry.entry_name == '残破的障碍物'
                                and self._gamepad_obstacle_hits < moved_node.entry.can_visited_times):
                            dx, dy = destination.center.x - current_position.x, destination.center.y - current_position.y
                            direction = ('right' if dx > 0 else 'left') if abs(dx) > abs(dy) else ('down' if dy > 0 else 'up')
                            self.ctx.controller.gamepad_ui_press(direction)
                            self._gamepad_obstacle_hits += 1
                            self._gamepad_move_checks = 0
                            return self.round_wait('继续撞击残破障碍物', wait=.7)
                if self._gamepad_move_checks >= 20:
                    return self.round_fail('未能确认手柄移动到相邻格')
                return self.round_wait('等待电视格子移动', wait=.25)
            if self._gamepad_waypoint is not None and not self._is_gamepad_map_stable(current_map, screen_time):
                return self.round_retry('等待路标所在画面稳定', wait=.25)
            self._pending_gamepad_move = None
            self._gamepad_move_screen = None
            if self._gamepad_waypoint is not None:
                # 路标使用屏幕坐标；保持路标前先排除头像已到旧框但镜头仍在平移的情况。
                source_size = previous_map.nodes[previous_map.current_idx].pos
                if (abs(current_node.pos.center.x - destination.center.x) > 4
                        or abs(current_node.pos.center.y - destination.center.y) > 4
                        or abs(current_node.pos.width - source_size.width) > 4
                        or abs(current_node.pos.height - source_size.height) > 4):
                    self._gamepad_waypoint = None
            if self._gamepad_waypoint is not None:
                _, waypoint_pos = self._gamepad_waypoint
                if (waypoint_pos.x1 <= moved_node.pos.center.x < waypoint_pos.x2
                        and waypoint_pos.y1 <= moved_node.pos.center.y < waypoint_pos.y2):
                    self._gamepad_waypoint = None
            entry_name = moved_node.entry.entry_name
            should_handle = (entry_name in self._entry_event_handlers
                             and entry_name not in ('门扉禁闭-善战', '门扉禁闭-侵蚀')
                             and not self.ctx.withered_domain.had_been_entry(entry_name))
            self.ctx.withered_domain.update_context_after_move(previous_map, moved_node, update_current=False)
            if (destination.width > current_node.pos.width * 1.5
                    or destination.height > current_node.pos.height * 1.5):
                # 双重危机的大电视在战后拆为小格；丢弃旧大格的合并缓存，再识别新拓扑。
                self.ctx.withered_domain.map_service.clear_map_result()
            self._handled_events.clear()
            if should_handle:
                op_result = self._entry_event_handlers[entry_name](self.ctx).execute()
                if not op_result.success:
                    return self.round_retry('格子入口事件处理失败', wait=1)
                self._handled_events.update(self._entry_events.get(entry_name, []))
            return self.round_wait('已确认电视格子移动')

        if self.ctx.controller.background_mode and not self._is_gamepad_map_stable(current_map, screen_time):
            return self.round_retry('等待电视地图缩放稳定', wait=.25)

        target_node: HollowZeroMapNode = self.ctx.withered_domain.get_next_to_move(current_map)
        if target_node is None:
            return None

        waypoint_node = None
        if self.ctx.controller.background_mode and self._gamepad_waypoint is not None:
            waypoint_name, waypoint_pos = self._gamepad_waypoint
            candidates = [node for node in current_map.nodes if node.entry.entry_name == waypoint_name
                          and waypoint_pos.x1 <= node.pos.center.x < waypoint_pos.x2
                          and waypoint_pos.y1 <= node.pos.center.y < waypoint_pos.y2]
            if len(candidates) == 1 and hollow_pathfinding.get_first_adjacent_node(current_map, candidates[0]) is not None:
                waypoint_node = candidates[0]
            else:
                self._gamepad_waypoint = None
        if waypoint_node is None:
            target_node, special_result = self._before_move(current_map, target_node)
            if special_result is not None:
                return special_result

        # if target_node.entry.entry_name == '不宜久留':  # 测试代码 在特殊情况停下
        #     return self.round_fail('不宜久留')
        next_to_move = waypoint_node if waypoint_node is not None else target_node.next_node_to_move
        if self.ctx.controller.background_mode:
            # 旧寻路按鼠标点击次数计费，零成本格的首节点可能绕行；手柄需逐格到达同一路标。
            waypoint_node = next_to_move
            next_to_move = hollow_pathfinding.get_first_adjacent_node(current_map, next_to_move)

        # 999 是寻路兜底策略的特殊标识 是在识别识别的情况下使用的
        pathfinding_success = next_to_move is not None and next_to_move.path_step_cnt != 999
        if not pathfinding_success:
            self._save_debug_image(screen)
            if next_to_move is None:
                return self.round_retry('自动寻路失败')
        log.info(f"前往目标: [{target_node.entry.entry_name}] 当前移动: [{next_to_move.entry.entry_name}]")

        # 寻路失败的话 间隔1秒才尝试一次兜底策略的移动
        if not pathfinding_success and screen_time - self._last_move_time < 1:
            return self.round_retry('自动寻路失败')

        if pathfinding_success:
            self.ctx.withered_domain.check_info_before_move(screen, current_map)
            # self._try_click_speed_up(screen)  # 可以在游戏内设置继承上一次
            extra_finished = self._check_extra_task_finished(screen, current_map)
            if extra_finished:
                return self.round_success(HollowRunner.STATUS_LEAVE)

        self._last_move_time = screen_time
        if self.ctx.controller.background_mode:
            adjacent = [current_map.nodes[index] for index in current_map.edges.get(current_map.current_idx, [])]
            if not current_map.is_valid_map or next_to_move not in adjacent or not pathfinding_success:
                return self.round_fail('后台寻路未确认相邻格，不使用随机移动')
            if hollow_pathfinding.get_rail_exit(current_map, next_to_move) is None:
                return self.round_fail('轨道出口未唯一确定，未发送移动')
            source = current_map.nodes[current_map.current_idx].pos.center
            destination = next_to_move.pos.center
            dx, dy = destination.x - source.x, destination.y - source.y
            direction = ('right' if dx > 0 else 'left') if abs(dx) > abs(dy) else ('down' if dy > 0 else 'up')
            self.ctx.controller.gamepad_ui_press(direction)
            # 路过空格期间固定原点击路标，避免每走一格重新选路而在两条等价路径之间往返。
            self._gamepad_waypoint = ((waypoint_node.entry.entry_name, waypoint_node.pos)
                                      if waypoint_node is not next_to_move else None)
            self._gamepad_obstacle_hits = 1 if next_to_move.entry.entry_name == '残破的障碍物' else 0
            self._gamepad_move_checks = 0
            self._gamepad_map_candidate = None
            self._pending_gamepad_move = (current_map, next_to_move)
            self._gamepad_move_screen = screen.copy()
            return self.round_wait('已发送相邻格方向，等待画面确认', wait=.25)
        to_click = self.get_map_node_pos_to_click(screen, next_to_move)
        self.ctx.controller.click(to_click)
        # 每个格子大概需要0.25秒移动 再加一秒等待格子事件触发
        move_time = next_to_move.path_node_cnt * 0.25 + 1
        time.sleep(move_time)

        # 如果是特殊需要选项的格子 则使用对应的事件指令处理 可以同时用来等待移动的时间
        op: Optional[ZOperation] = None
        entry_name = next_to_move.entry.entry_name
        if entry_name in self._entry_event_handlers and not self.ctx.withered_domain.had_been_entry(entry_name):
            op = self._entry_event_handlers[entry_name](self.ctx)

        self.ctx.withered_domain.update_context_after_move(current_map, next_to_move)
        self._handled_events.clear()

        # 如果是特殊需要选项的格子 则使用对应的事件指令处理 可以同时用来等待移动的时间
        entry_name = next_to_move.entry.entry_name
        if op is not None:
            op_result = op.execute()
            if op_result.success:
                events = self._entry_events.get(entry_name, [])
                for e in events:
                    self._handled_events.add(e)
                return self.round_wait()
            else:
                return self.round_retry()

        return self.round_wait()

    def _before_move(self, current_map: HollowZeroMap,
                     target_node: HollowZeroMapNode) -> tuple[HollowZeroMapNode, OperationRoundResult | None]:
        """
        移动前的扩展点 子类可以修改目标 或者直接返回本轮的结果
        :param current_map: 当前地图
        :param target_node: 寻路得到的目标
        :return: 最终的目标；不为None的本轮结果
        """
        return target_node, None

    def get_map_node_pos_to_click(self, screen: MatLike, node: HollowZeroMapNode) -> Point:
        """
        获取格子的点击位置 要避开画面上可能出现的选项
        :param screen: 游戏画面
        :param node: 需要点击的格子
        :return: 需要点击的位置
        """
        # 识别画面上是否有选项
        opt = hollow_event_utils.check_entry_opt_pos_at_right(self.ctx, screen, set())
        if opt is None:  # 没有选项的时候 随便点击
            return node.pos.center
        else:
            # 有选项的时候 点击离选项最远的一个角
            node_rect: Rect = node.pos
            opt_rect: Rect = opt.rect

            # 格子的4个角 往里面移动一点 防止最终点击到格子外
            offset = 15
            pos_list = [
                Point(node_rect.x1, node_rect.y1) + Point(offset, offset),
                Point(node_rect.x1, node_rect.y2) + Point(offset, -offset),
                Point(node_rect.x2, node_rect.y1) + Point(-offset, offset),
                Point(node_rect.x2, node_rect.y2) + Point(-offset, -offset),
            ]

            # 找出离选项中点最远的点
            target_pos = None
            for pos in pos_list:
                if target_pos is None or cal_utils.distance_between(pos, opt_rect.center) > cal_utils.distance_between(target_pos, opt_rect.center):
                    target_pos = pos

            return target_pos

    def _try_click_speed_up(self, screen: MatLike) -> None:
        # 快进
        if not self.ctx.withered_domain.speed_up_clicked:
            result = self.round_by_find_and_click_area(screen, '零号空洞-事件', '快进')
            time.sleep(0.2)
            if result.is_success:
                self.ctx.withered_domain.speed_up_clicked = True

    def _check_extra_task_finished(self, screen: MatLike, current_map: HollowZeroMap) -> bool:
        """
        判断额外业绩是否刷完了
        :param screen:
        :param current_map:
        :return:
        """
        level_info = self.ctx.withered_domain.level_info

        if self.run_record.is_finished_by_day():
            # 已经完成了
            return True

        # 完成指定次数后才会触发刷业绩的选项
        if not self.run_record.is_finished_by_weekly_times():
            return False

        if self.config.extra_task == HollowZeroExtraTask.NONE.value.value:
            return False

        # 判断是否到达层数退出
        extra_exit_by_level: bool = False
        if current_map.contains_entry('业绩考察点空'):
            self.run_record.no_eval_point = True
        if self.config.extra_exit == HollowZeroExtraExitEnum.LEVEL_2_EVA.value.value:
            if level_info.level > 2 or (level_info.level == 2 and level_info.phase > 1):  # 已经过了指定的楼层
                extra_exit_by_level = True
            if level_info.level == 2 and level_info.phase == 1:
                if self.ctx.withered_domain.had_been_entry('业绩考察点') and not current_map.contains_entry('业绩考察点'):
                    extra_exit_by_level = True
                if current_map.contains_entry('业绩考察点空'):
                    extra_exit_by_level = True
        elif self.config.extra_exit == HollowZeroExtraExitEnum.LEVEL_3_EVA.value.value:
            if level_info.level == 3 and level_info.phase > 1:  # 已经过了指定的楼层
                extra_exit_by_level = True
            if level_info.level == 3 and level_info.phase == 1:
                if self.ctx.withered_domain.had_been_entry('业绩考察点') and not current_map.contains_entry('业绩考察点'):
                    extra_exit_by_level = True
                if current_map.contains_entry('业绩考察点空'):
                    extra_exit_by_level = True


        if self.config.extra_task == HollowZeroExtraTask.EVA_POINT.value.value:
            if self.config.extra_exit == HollowZeroExtraExitEnum.COMPLETE.value.value:
                return False
            else:
                return extra_exit_by_level
        elif self.config.extra_task == HollowZeroExtraTask.PERIOD_REWARD.value.value:
            # 周期性奖励在关键进展的战斗后判断
            if self.config.extra_exit == HollowZeroExtraExitEnum.COMPLETE.value.value:
                return False
            else:
                return extra_exit_by_level

        return False

    def _save_debug_image(self, screen: MatLike,enforce:bool = False) -> None:
        """
        保存图片用于优化模型
        """
        if not ( self.ctx.env_config.is_debug or enforce ):
            return
        now = time.time()
        if now - self._last_save_image_time < 1:
            return
        self._last_save_image_time = now
        from one_dragon.utils import debug_utils
        debug_utils.save_debug_image(screen, prefix='pathfinding_fail')

    @node_from(from_name='画面识别', status=STATUS_LEAVE)
    @operation_node(name='离开空洞')
    def exit_hollow(self) -> OperationRoundResult:
        op = HollowExitByMenu(self.ctx)
        result = op.execute()
        if result.success:
            self.run_record.add_daily_times()
        return self.round_by_op_result(result)

    @node_from(from_name='画面识别', status='通关-完成')
    @operation_node(name='通关-完成', node_max_retry_times=60)
    def mission_complete(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            if all(self.round_by_find_area(self.last_screenshot, '零号空洞-事件', name).is_success
                   for name in ('手柄-通关标题', '手柄-通关完成')):
                self.ctx.controller.gamepad_ui_press('back')
                return self.round_retry('等待退出空洞结算', wait=1)
            result = self.round_by_find_area(self.last_screenshot, '零号空洞-入口', '街区')
            at_type_selection = all(
                self.round_by_find_area(self.last_screenshot, '零号空洞-入口', name).is_success
                for name in ('手柄-资质考核', '手柄-施工废墟')
            )
            if result.is_success or at_type_selection:
                self.run_record.add_daily_times()
                return self.round_success('已返回空洞入口')
            return self.round_retry('等待空洞入口', wait=1)
        result = self.round_by_find_and_click_area(self.last_screenshot, '零号空洞-事件', '通关-完成')
        if result.is_success:
            reward = self.round_by_find_area(self.last_screenshot, '零号空洞-战斗', '通关-丁尼奖励')
            if not reward.is_success:
                # 领满奖励了
                self.run_record.period_reward_complete = True
                self.save_screenshot()
            else:
                # 防止因为动画效果 奖励还没有出现 就出现了按钮
                self.run_record.period_reward_complete = False
            return self.round_wait(result.status, wait=1)

        # 一直尝试点击直到出现街区
        result = self.round_by_find_area(self.last_screenshot, '零号空洞-入口', '街区')
        if result.is_success:
            self.run_record.add_daily_times()
            return self.round_success(result.status)

        return self.round_retry(result.status, wait=1)


def __debug():
    ctx = ZContext()
    ctx.init_by_config()
    ctx.run_context.start_running()
    ctx.init_ocr()
    ctx.withered_domain.init_before_hollow_start('旧都列车', '旧都列车-核心')
    op = HollowRunner(ctx)
    # from one_dragon.utils import debug_utils
    # screen = debug_utils.get_debug_image('_1723977819253')
    # result = op.round_by_find_and_click_area(screen, '零号空洞-事件', '快进')
    # print(result.is_success)
    op.execute()


if __name__ == '__main__':
    __debug()
