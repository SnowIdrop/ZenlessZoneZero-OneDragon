from typing import ClassVar

from one_dragon.base.operation.application import application_const
from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_notify import NotifyTiming, node_notify
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from zzz_od.application.charge_plan.charge_plan_config import ChargePlanItem
from zzz_od.application.notorious_hunt import notorious_hunt_const
from zzz_od.application.notorious_hunt.notorious_hunt_config import NotoriousHuntConfig
from zzz_od.application.notorious_hunt.notorious_hunt_run_record import (
    NotoriousHuntRunRecord,
)
from zzz_od.application.zzz_application import ZApplication
from zzz_od.context.zzz_context import ZContext
from zzz_od.operation.back_to_normal_world import BackToNormalWorld
from zzz_od.operation.challenge_mission.check_next_after_battle import (
    ChooseNextOrFinishAfterBattle,
)
from zzz_od.operation.compendium.notorious_hunt import NotoriousHunt
from zzz_od.operation.compendium.tp_by_compendium import TransportByCompendium


class NotoriousHuntApp(ZApplication):

    """恶名狩猎:按计划打周限高难狩猎本(每周按周历轮换)。每周 3 次免费奖励(不耗电量)、进入战斗。"""

    STATUS_NO_PLAN: ClassVar[str] = '未配置恶名狩猎计划'
    STATUS_ROUND_FINISHED: ClassVar[str] = '本轮计划已完成'

    def __init__(self, ctx: ZContext):
        """
        恶名狩猎
        """
        ZApplication.__init__(
            self,
            ctx=ctx, app_id=notorious_hunt_const.APP_ID,
            op_name=notorious_hunt_const.APP_NAME,
        )

        self.config: NotoriousHuntConfig = self.ctx.run_context.get_config(
            app_id=notorious_hunt_const.APP_ID,
            instance_idx=self.ctx.current_instance_idx,
            group_id=application_const.DEFAULT_GROUP_ID,
        )

        self.run_record: NotoriousHuntRunRecord = self.ctx.run_context.get_run_record(
            app_id=notorious_hunt_const.APP_ID,
            instance_idx=self.ctx.current_instance_idx,
        )

    def handle_init(self) -> None:
        """
        执行前的初始化 由子类实现
        注意初始化要全面 方便一个指令重复使用
        """
        self.next_plan: ChargePlanItem | None = None
        self.last_tried_plan: ChargePlanItem | None = None
        self._reward_navigation_started: bool = False
        self._reward_claim_requested: bool = False

    @operation_node(name='开始恶名狩猎', is_start_node=True)
    def start_hunt(self) -> OperationRoundResult:
        # 每轮开始复位游标并清空本轮跳过标记
        self.last_tried_plan = None
        for plan in self.config.plan_list:
            plan.skipped = False
        return self.round_success()

    @node_from(from_name='开始恶名狩猎')
    @node_from(from_name='跳过或结束计划')
    @node_from(from_name='判断剩余次数')
    @operation_node(name='查找下一条计划')
    def find_next_plan(self) -> OperationRoundResult:
        if len(self.config.plan_list) == 0:
            return self.round_success(NotoriousHuntApp.STATUS_NO_PLAN)

        # 全部计划已完成：开启循环则清零重开，否则结束本轮
        if self.config.all_plan_finished():
            if self.config.loop:
                self.last_tried_plan = None
                self.config.reset_plans()
            else:
                return self.round_success(NotoriousHuntApp.STATUS_ROUND_FINISHED)

        self.next_plan = self.config.get_next_plan(self.last_tried_plan)
        if self.next_plan is None:
            return self.round_success(NotoriousHuntApp.STATUS_ROUND_FINISHED)
        return self.round_success()

    @node_from(from_name='查找下一条计划')
    @operation_node(name='前往大世界')  # 特训目标查找失败可能把快捷手册列表滑到底部，返回大世界后重置列表位置
    def back_before_open_compendium(self) -> OperationRoundResult:
        op = BackToNormalWorld(self.ctx, ensure_normal_world=True)
        return self.round_by_op_result(op.execute())

    @node_from(from_name='前往大世界')
    @operation_node(name='传送')
    def transport(self) -> OperationRoundResult:
        op = TransportByCompendium(self.ctx,
                                   self.next_plan.tab_name,
                                   self.next_plan.category_name,
                                   self.next_plan.mission_type_name)
        return self.round_by_op_result(op.execute())

    @node_from(from_name='传送', success=False, status='找不到 代理人方案培养')
    @node_from(from_name='恶名狩猎', status=ChooseNextOrFinishAfterBattle.STATUS_AGENT_PLAN_FINISHED)
    @operation_node(name='跳过或结束计划')
    def skip_plan_or_finish(self) -> OperationRoundResult:
        # 特训目标找不到代理人头像或已达成，提前跳过/结束
        self.next_plan.skipped = True
        self.last_tried_plan = self.next_plan
        return self.round_success()

    @node_from(from_name='传送')
    @operation_node(name='恶名狩猎')
    def notorious_hunt(self) -> OperationRoundResult:
        op = NotoriousHunt(self.ctx, self.next_plan, use_charge_power=False)
        return self.round_by_op_result(op.execute())

    @node_from(from_name='恶名狩猎', success=True)
    @node_from(from_name='恶名狩猎', success=False)
    @operation_node(name='判断剩余次数')
    def check_left_times(self) -> OperationRoundResult:
        if self.run_record.left_times == 0:
            return self.round_success(NotoriousHunt.STATUS_NO_LEFT_TIMES)

        if self.previous_node.is_success:
            # 成功完成一次后复位游标，从头重新查找
            self.last_tried_plan = None
        else:
            # 战斗失败：标记当前计划本轮跳过，避免在同一轮里反复死磕
            self.next_plan.skipped = True
            self.last_tried_plan = self.next_plan
        return self.round_success()

    @node_from(from_name='判断剩余次数', status=NotoriousHunt.STATUS_NO_LEFT_TIMES)
    @node_from(from_name='恶名狩猎', status=NotoriousHunt.STATUS_NO_LEFT_TIMES)
    @node_from(from_name='查找下一条计划', status=STATUS_NO_PLAN)
    @node_from(from_name='查找下一条计划', status=STATUS_ROUND_FINISHED)
    @operation_node(name='点击奖励入口', node_max_retry_times=8)
    def click_reward_entry(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            if not self._reward_navigation_started:
                # 空计划也要先进入恶名狩猎分类，不能在原页面点击旧版奖励坐标。
                result = TransportByCompendium(self.ctx, '训练', '恶名狩猎').execute()
                if not result.success:
                    return self.round_by_op_result(result)
                self._reward_navigation_started = True
                return self.round_retry('已进入恶名狩猎分类', wait=.5)
            if self.round_by_find_area(
                self.last_screenshot, '恶名狩猎', '手柄-周期挑战标题',
            ).is_success:
                return self.round_success()
            if not self.round_by_find_area(
                self.last_screenshot, '恶名狩猎', '手柄-周期挑战入口',
            ).is_success:
                return self.round_retry('未识别周期挑战入口', wait=.5)
            self.round_by_click_area('恶名狩猎', '手柄-周期挑战入口')
            return self.round_retry('打开周期挑战', wait=.5)
        return self.round_by_click_area(
            '恶名狩猎', '奖励入口',
            success_wait=1, retry_wait=1
        )

    @node_from(from_name='点击奖励入口')
    @node_notify(when=NotifyTiming.CURRENT_DONE)
    @operation_node(name='全部领取', node_max_retry_times=2)
    def claim_all(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            if self._reward_claim_requested:
                result = self.round_by_find_and_click_area(
                    self.last_screenshot, '快捷手册', '活跃度奖励-确认',
                )
                if result.is_success:
                    return self.round_retry('关闭周期挑战奖励消息', wait=.5)
            if not self.round_by_find_area(
                self.last_screenshot, '恶名狩猎', '手柄-周期挑战标题',
            ).is_success:
                return self.round_retry('未确认周期挑战奖励页', wait=.5)
            if not self.round_by_find_area(
                self.last_screenshot, '恶名狩猎', '手柄-全部领取',
            ).is_success:
                return self.round_retry('未识别全部领取按钮', wait=.5)
            enabled = self.round_by_find_area(self.last_screenshot, '恶名狩猎', '手柄-可领取奖励').is_success
            if not enabled:
                if self.round_by_find_area(self.last_screenshot, '恶名狩猎', '手柄-暂无奖励').is_success:
                    return self.round_success('当前无可领取周期挑战奖励')
                return self.round_retry('未确认领取按钮是否可用', wait=.5)
            if not self._reward_claim_requested:
                self.ctx.controller.gamepad_ui_press('secondary')
                self._reward_claim_requested = True
            return self.round_retry('等待周期挑战奖励领取结果', wait=1)
        return self.round_by_find_and_click_area(
            self.last_screenshot, '恶名狩猎', '全部领取',
            success_wait=1, retry_wait=0.5
        )

    @node_from(from_name='点击奖励入口', success=False)
    @node_from(from_name='全部领取')
    @node_from(from_name='全部领取', success=False)
    @operation_node(name='返回大世界')
    def back_to_world(self) -> OperationRoundResult:
        op = BackToNormalWorld(self.ctx)
        result = op.execute()
        if self.ctx.controller.background_mode and self.previous_node.is_fail:
            # 返回只是清理现场，不能把未进入奖励页或未识别领取按钮改记为成功。
            return self.round_fail(self.previous_node.status)
        return self.round_by_op_result(result)
