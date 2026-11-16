import time
from typing import Optional, ClassVar

from cv2.typing import MatLike

from one_dragon.base.geometry.rectangle import Rect
from one_dragon.base.operation.operation import Operation
from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils.i18_utils import gt
from one_dragon.utils import cv2_utils, str_utils
from one_dragon.utils.log_utils import log
from zzz_od.application.hollow_zero.withered_domain.withered_domain_run_record import WitheredDomainRunRecord
from zzz_od.context.zzz_context import ZContext
from zzz_od.hollow_zero.event import hollow_event_utils
from zzz_od.hollow_zero.event.choose_resonium import ChooseResonium
from zzz_od.hollow_zero.event.confirm_resonium import ConfirmResonium
from zzz_od.hollow_zero.game_data.hollow_zero_event import HollowZeroSpecialEvent
from zzz_od.operation.zzz_operation import ZOperation


class HollowBattle(ZOperation):

    STATUS_NEED_SPECIAL_MOVE: ClassVar[str] = '需要移动'
    STATUS_NO_NEED_SPECIAL_MOVE: ClassVar[str] = '不需要移动'
    STATUS_FAIL_TO_MOVE: ClassVar[str] = '移动失败'

    def __init__(self, ctx: ZContext, is_critical_stage: bool = False):
        """
        确定进入战斗后调用
        战斗后的按钮点击退出交由外层实现
        :param ctx:
        """
        event_name = HollowZeroSpecialEvent.IN_BATTLE.value.event_name
        ZOperation.__init__(
            self, ctx,
            op_name=gt(event_name, 'game')
        )

        self.run_record: Optional[WitheredDomainRunRecord] = self.ctx.run_context.get_run_record(
            instance_idx=self.ctx.current_instance_idx,
            app_id=self.ctx.withered_domain.app_id,
        )

        self.is_critical_stage: bool = is_critical_stage  # 是否关键进展
        self.move_times: int = 0  # 向前移动的次数
        self.turn_times: int = 0  # 转动的次数
        self.last_distance: Optional[float] = None  # 上次移动前的距离
        self.last_stuck_distance: Optional[float] = None  # 上次受困显示的距离
        self.stuck_move_direction: int = 0  # 受困时移动的方向
        self.last_distance_to_turn: Optional[float] = None  # 上次转向的距离

    def handle_init(self):
        self.distance_pos: Optional[Rect] = None  # 显示距离的区域
        self._gamepad_result_retry: bool = False  # 取消晚到暂离弹窗后，才允许再次确认结果

    @operation_node(name='加载自动战斗指令', is_start_node=True)
    def load_auto_op(self) -> OperationRoundResult:
        self.ctx.auto_battle_context.init_auto_op(
            sub_dir='auto_battle',
            op_name=self.ctx.withered_domain.challenge_config.auto_battle,
        )
        return self.round_success()

    @node_from(from_name='加载自动战斗指令')
    @operation_node(name='等待战斗画面加载', node_max_retry_times=60)
    def wait_battle_screen(self) -> OperationRoundResult:
        if (self.ctx.controller.background_mode
                and hollow_event_utils.is_challenge_result(self.ctx, self.last_screenshot)):
            self.ctx.auto_battle_context.stop_auto_battle()
            return self.round_success('已在挑战结果')
        result = self.round_by_find_area(self.last_screenshot, '战斗画面', '按键-普通攻击', retry_wait_round=1)
        return result

    @node_from(from_name='等待战斗画面加载')
    @operation_node(name='识别特殊移动')
    def check_special_move(self):
        self.check_distance_to_move(self.last_screenshot)

        if self.ctx.auto_battle_context.with_distance_times >= 10:
            return self.round_success(HollowBattle.STATUS_NEED_SPECIAL_MOVE)
        if self.ctx.auto_battle_context.without_distance_times >= 10:
            self.ctx.auto_battle_context.start_auto_battle()
            return self.round_success(HollowBattle.STATUS_NO_NEED_SPECIAL_MOVE)

        return self.round_wait()

    @node_from(from_name='识别特殊移动', status=STATUS_NEED_SPECIAL_MOVE)
    @operation_node(name='副本特殊移动')
    def special_move(self):
        if (self.ctx.withered_domain.level_info.is_mission_type('旧都列车', 2)
            and self.ctx.withered_domain.level_info.level == 2):
            self.ctx.controller.move_w(press=True, press_time=1.5)
        else:
            self.ctx.controller.move_w(press=True, press_time=1.5)

        return self.round_success()

    @node_from(from_name='副本特殊移动')
    @node_from(from_name='自动战斗', status=STATUS_NEED_SPECIAL_MOVE)
    @operation_node(name='向前移动准备战斗')
    def move_to_battle(self) -> OperationRoundResult:
        self.check_distance_to_move(self.last_screenshot)

        if self.distance_pos is None:
            if self.ctx.auto_battle_context.without_distance_times >= 10:
                self.ctx.auto_battle_context.start_auto_battle()
                return self.round_success()
            else:
                return self.round_wait(wait=0.02)

        if self.move_times >= 20 or self.turn_times >= 60:
            # 移动比较久也没到 就自动退出了
            return self.round_fail(HollowBattle.STATUS_FAIL_TO_MOVE)

        current_distance = self.ctx.auto_battle_context.last_check_distance
        if self.last_distance is not None and abs(self.last_distance - current_distance) < 0.5:
            log.info('上次移动后距离没有发生变化 尝试脱困')
            if self.last_stuck_distance is not None and abs(self.last_stuck_distance - current_distance) < 0.5:
                # 困的时候显示的距离跟上次困住的一样 代表脱困方向不对 换一个
                log.info('上次脱困后距离没有发生变化 更换脱困方向')
                self.stuck_move_direction += 1
                if self.stuck_move_direction >= 6:
                    self.stuck_move_direction = 0

            self.last_distance = current_distance
            self.last_stuck_distance = current_distance

            self._get_rid_of_stuck()

            return self.round_wait(wait=0.5)

        pos = self.distance_pos.center
        if pos.x < 900:
            self.ctx.controller.turn_by_distance(-50)
            self.turn_times += 1
            return self.round_wait(wait=0.5)
        elif pos.x > 1100:
            self.ctx.controller.turn_by_distance(+50)
            self.turn_times += 1
            return self.round_wait(wait=0.5)
        else:
            self.last_distance = current_distance
            press_time = self.ctx.auto_battle_context.last_check_distance / 7.2  # 朱鸢测出来的速度
            self.ctx.controller.move_w(press=True, press_time=press_time, release=True)
            self.move_times += 1
            self.last_distance_to_turn = None  # 移动完后重新识别
            return self.round_wait(wait=0.5)

    def _get_rid_of_stuck(self):
        log.info('本次脱困方向 %s' % self.stuck_move_direction)
        if self.stuck_move_direction == 0:  # 向左走
            self.ctx.controller.move_a(press=True, press_time=1, release=True)
        elif self.stuck_move_direction == 1:  # 向右走
            self.ctx.controller.move_d(press=True, press_time=1, release=True)
        elif self.stuck_move_direction == 2:  # 后左前 1秒
            self.ctx.controller.move_s(press=True, press_time=1, release=True)
            self.ctx.controller.move_a(press=True, press_time=1, release=True)
            self.ctx.controller.move_w(press=True, press_time=1, release=True)
        elif self.stuck_move_direction == 3:  # 后右前 1秒
            self.ctx.controller.move_s(press=True, press_time=1, release=True)
            self.ctx.controller.move_d(press=True, press_time=1, release=True)
            self.ctx.controller.move_w(press=True, press_time=1, release=True)
        elif self.stuck_move_direction == 4:  # 后左前 2秒
            self.ctx.controller.move_s(press=True, press_time=2, release=True)
            self.ctx.controller.move_a(press=True, press_time=2, release=True)
            self.ctx.controller.move_w(press=True, press_time=2, release=True)
        elif self.stuck_move_direction == 5:  # 后右前 2秒
            self.ctx.controller.move_s(press=True, press_time=2, release=True)
            self.ctx.controller.move_d(press=True, press_time=2, release=True)
            self.ctx.controller.move_w(press=True, press_time=2, release=True)

    @node_from(from_name='识别特殊移动', status=STATUS_NO_NEED_SPECIAL_MOVE)
    @node_from(from_name='向前移动准备战斗')
    @operation_node(name='自动战斗', timeout_seconds=600, mute=True)
    def auto_battle(self) -> OperationRoundResult:
        self.move_times = 0
        self.turn_times = 0
        if self.ctx.controller.background_mode:
            if self._cancel_gamepad_suspend():
                return self.round_wait('等待关闭暂离提示', wait=.5)
            if hollow_event_utils.is_challenge_result(self.ctx, self.last_screenshot):
                self.ctx.auto_battle_context.stop_auto_battle()
                return self.round_success('零号空洞-挑战结果')
            if all(self.round_by_find_area(self.last_screenshot, '零号空洞-事件', name).is_success
                   for name in ('手柄-通关标题', '手柄-通关完成')):
                self.ctx.auto_battle_context.stop_auto_battle()
                return self.round_success('普通战斗-完成')
            if all(self.round_by_find_area(self.last_screenshot, '零号空洞-事件', name).is_success
                   for name in ('手柄-探索总结', '手柄-总结委托')):
                # 结算出现时残余战斗输入可能打开总结，先停手柄并返回已确认的结算页。
                self.ctx.auto_battle_context.stop_auto_battle()
                self.ctx.controller.gamepad_ui_press('back')
                return self.round_wait('返回空洞结算', wait=.5)
        if self.ctx.auto_battle_context.last_check_end_result is not None:
            self.ctx.auto_battle_context.stop_auto_battle()
            return self.round_success(status=self.ctx.auto_battle_context.last_check_end_result)

        if self.ctx.auto_battle_context.with_distance_times >= 5:
            self.ctx.auto_battle_context.stop_auto_battle()
            return self.round_success(status=HollowBattle.STATUS_NEED_SPECIAL_MOVE)

        self.ctx.auto_battle_context.check_battle_state(
            self.last_screenshot, self.last_screenshot_time,
            check_battle_end_normal_result=True,
            check_battle_end_hollow_result=True,
            check_distance=True,
        )

        return self.round_wait(wait=self.ctx.battle_assistant_config.screenshot_interval)

    def _cancel_gamepad_suspend(self) -> bool:
        """首领结算残留 X 会打开暂离弹窗；停战斗输入后取消，保留当前探索。"""
        if not all(self.round_by_find_area(self.last_screenshot, '零号空洞-战斗', name).is_success
                   for name in ('手柄-暂离提示', '手柄-暂离取消')):
            return False
        self.ctx.auto_battle_context.stop_auto_battle()
        self.ctx.controller.gamepad_ui_press('back')
        return True

    @node_from(from_name='自动战斗', status='零号空洞-结算周期上限')
    @operation_node(name='结算周期上限')
    def period_reward_full(self) -> OperationRoundResult:
        time.sleep(1)  # 第一次稍等等一段时间 避免按键还不能响应
        self.run_record.period_reward_complete = True
        return self.round_by_find_and_click_area(self.last_screenshot, '零号空洞-战斗', '结算周期上限-确认',
                                                 success_wait=1, retry_wait=1)

    @node_from(from_name='结算周期上限')
    @node_from(from_name='等待战斗画面加载', status='已在挑战结果')
    @node_from(from_name='自动战斗', status='零号空洞-挑战结果')
    @operation_node(name='战斗结果-确定')
    def after_battle(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            if self._cancel_gamepad_suspend():
                return self.round_retry('等待关闭暂离提示', wait=.5)
            if not hollow_event_utils.is_challenge_result(self.ctx, self.last_screenshot):
                return self.round_retry('等待挑战结果', wait=.5)
            area = self.ctx.screen_loader.get_area('零号空洞-战斗', '战斗结果-确定')
            if not self.round_by_ocr(self.last_screenshot, '确定', area=area, lcs_percent=1).is_success:
                return self.round_retry('等待结果确认按钮', wait=.5)
            self.ctx.controller.gamepad_ui_press('confirm')
            return self.round_success('手柄结果已确认', wait=.5)
        # 找到后稍微等待: 1.按钮刚出来的时候按不会有响应 2. 奖励列表可能还没有出现
        time.sleep(2)

        # 有时候可能会识别到背景上的挑战结果 这时候也尝试点
        result = self.round_by_find_and_click_area(self.last_screenshot, '零号空洞-战斗', '结算周期上限-确认')
        if result.is_success:
            return self.round_wait()  # 每次开始都有等待 这里就不等了

        area = self.ctx.screen_loader.get_area('零号空洞-战斗', '战斗结果-确定')
        result = self.round_by_ocr_and_click(self.last_screenshot, '确定', area=area)
        if result.is_success:
            return self.round_success(result.status, wait=1)

        # 匹配不到的时候 随便点击 防止有一些新的对话框出现没有处理到
        self.round_by_click_area('零号空洞-战斗', '战斗结果-确定')
        return self.round_retry(result.status, wait=1)

    @node_from(from_name='自动战斗', status='普通战斗-完成')
    @operation_node(name='普通战斗-完成')
    def mission_complete(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            # 手柄结算的奖励位置不同，缺少旧版丁尼图标不能证明周期奖励已满。
            return self.round_success(status='普通战斗-完成')
        # 在battle_context里会判断这个的出现
        # 找到后稍微等待: 1.按钮刚出来的时候按不会有响应 2. 奖励列表可能还没有出现
        time.sleep(2)
        screen = self.screenshot()

        result = self.round_by_find_area(screen, '零号空洞-战斗', '通关-丁尼奖励')
        if not result.is_success:
            # 领满奖励了
            self.run_record.period_reward_complete = True
            self.save_screenshot()
        else:
            # 防止因为动画效果 奖励还没有出现 就出现了按钮
            self.run_record.period_reward_complete = False

        return self.round_success(status='普通战斗-完成')

    @node_from(from_name='战斗结果-确定', status='手柄结果已确认')
    @operation_node(name='等待手柄楼层切换', node_max_retry_times=30, timeout_seconds=60)
    def wait_gamepad_next_level(self) -> OperationRoundResult:
        # 以重新出现的探索画面确认转场，不能只凭发出 A 就记录下一层。
        if self._cancel_gamepad_suspend():
            self._gamepad_result_retry = True
            return self.round_retry('等待关闭暂离提示', wait=.5)
        if self._gamepad_result_retry and hollow_event_utils.is_challenge_result(self.ctx, self.last_screenshot):
            # 只重发被暂离弹窗阻断的确认，并用新截图复核，避免慢转场时连按 A 误选鸣徽。
            self.screenshot()
            result = self.after_battle()
            if result.is_success:
                self._gamepad_result_retry = False
            return self.round_retry(result.status)
        if self.round_by_find_area(self.last_screenshot, '零号空洞-战斗', '鸣徽-确定').is_success:
            # 战后诡术鸣徽可能先重构，确认卡片后才会恢复探索画面。
            result = ConfirmResonium(self.ctx).execute()
            if not result.success:
                return self.round_fail(result.status)
            return self.round_wait(wait=.5)
        area = self.ctx.screen_loader.get_area('零号空洞-事件', '底部-选择列表')
        if self.round_by_ocr(self.last_screenshot, '选择', area=area, lcs_percent=1).is_success:
            result = ChooseResonium(self.ctx).execute()
            if not result.success:
                return self.round_fail(result.status)
            return self.round_wait(wait=.5)
        level_info = self.ctx.withered_domain.level_info
        area = self.ctx.screen_loader.get_area('零号空洞-事件', '当前层数')
        text = self.ctx.ocr.run_ocr_single_line(cv2_utils.crop_image_only(self.last_screenshot, area.rect))
        observed_level = str_utils.get_positive_digits(text)
        if (level_info is None or observed_level not in (1, 2, 3)
                or (level_info.level != -1 and observed_level != level_info.level + 1)):
            return self.round_retry('未观察到下一层层数', wait=1)
        current_map = self.ctx.withered_domain.map_service.cal_current_map_by_screen(self.last_screenshot, self.last_screenshot_time)
        if current_map is None or not current_map.is_valid_map:
            return self.round_retry('等待下一层电视地图', wait=1)
        return self.round_success(data=observed_level)

    @node_from(from_name='战斗结果-确定')
    @node_from(from_name='等待手柄楼层切换')
    @operation_node(name='更新楼层信息')
    def update_level_info(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            self.ctx.withered_domain.update_to_next_level(observed_level=self.previous_node.data)
        else:
            self.ctx.withered_domain.update_to_next_level()
        return self.round_success()

    @node_from(from_name='自动战斗', status='普通战斗-撤退')
    @operation_node(name='战斗撤退')
    def battle_fail(self) -> OperationRoundResult:
        return self.round_by_find_and_click_area(self.last_screenshot, '战斗画面', '战斗结果-撤退',
                                                 success_wait=1, retry_wait=1)

    @node_from(from_name='自动战斗', success=False, status=Operation.STATUS_TIMEOUT)
    @node_from(from_name='向前移动准备战斗', success=False, status=STATUS_FAIL_TO_MOVE)
    @operation_node(name='移动失败')
    def move_fail(self) -> OperationRoundResult:
        self.ctx.auto_battle_context.stop_auto_battle()

        result = self.round_by_find_area(self.last_screenshot, '零号空洞-战斗', '退出战斗')
        if result.is_success:
            return self.round_success(wait=0.5)  # 稍微等一下让按钮可按

        return self.round_by_click_area('战斗画面', '菜单',
                                        success_wait=1, retry_wait=1)

    @node_from(from_name='移动失败')
    @operation_node(name='点击退出')
    def click_exit(self) -> OperationRoundResult:
        return self.round_by_find_and_click_area(self.last_screenshot, '零号空洞-战斗', '退出战斗',
                                                 success_wait=1, retry_wait=1)

    @node_from(from_name='点击退出')
    @operation_node(name='点击退出确认')
    def click_exit_confirm(self) -> OperationRoundResult:
        return self.round_by_find_and_click_area(self.last_screenshot, '零号空洞-战斗', '退出战斗-确认',
                                                 success_wait=1, retry_wait=1)

    @node_from(from_name='点击退出确认')
    @operation_node(name='等待退出', node_max_retry_times=20)
    def wait_exit(self) -> OperationRoundResult:
        return self.round_by_find_area(self.last_screenshot, '零号空洞-事件', '通关-完成',
                                       success_wait=2, retry_wait=1)  # 找到后稍微等待 按钮刚出来的时候按没有用

    def check_distance_to_move(self, screen: MatLike) -> None:
        mr = self.ctx.auto_battle_context.check_battle_distance(screen, self.last_distance_to_turn)

        if mr is None:
            self.distance_pos = None
        else:
            self.distance_pos = mr.rect
            self.last_distance_to_turn = mr.data

    def handle_pause(self, e=None):
        self.ctx.auto_battle_context.stop_auto_battle()

    def handle_resume(self, e=None):
        if self.current_node.node is not None and self.current_node.node.cn == '自动战斗':
            self.ctx.auto_battle_context.resume_auto_battle()


def __debug():
    ctx = ZContext()
    ctx.init()
    ctx.withered_domain.init_before_run()
    ctx.run_context.start_running()
    op = HollowBattle(ctx)
    op.execute()


if __name__ == '__main__':
    __debug()

