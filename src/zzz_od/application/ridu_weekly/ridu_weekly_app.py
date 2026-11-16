from cv2.typing import MatLike

from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_notify import node_notify, NotifyTiming
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.base.screen import screen_utils
from zzz_od.application.ridu_weekly import ridu_weekly_const
from zzz_od.application.zzz_application import ZApplication
from zzz_od.context.zzz_context import ZContext
from zzz_od.operation.back_to_normal_world import BackToNormalWorld


class RiduWeeklyApp(ZApplication):

    """丽都周纪:领取周纪的积分/奖励。周限、无体力消耗。"""

    def __init__(self, ctx: ZContext):
        ZApplication.__init__(
            self,
            ctx=ctx,
            app_id=ridu_weekly_const.APP_ID,
            op_name=ridu_weekly_const.APP_NAME,
        )

    @operation_node(name='返回大世界', is_start_node=True)
    def back_at_first(self) -> OperationRoundResult:
        op = BackToNormalWorld(self.ctx)
        return self.round_by_op_result(op.execute())

    @node_from(from_name='返回大世界')
    @operation_node(name='日常')
    def choose_daily(self) -> OperationRoundResult:
        return self.round_by_goto_screen(screen_name='快捷手册-日常')

    @node_from(from_name='日常')
    @operation_node(name='丽都周纪')
    def click_schedule(self) -> OperationRoundResult:
        return self.round_by_find_and_click_area(self.last_screenshot, '丽都周纪', '丽都周纪',
                                                 success_wait=2, retry_wait=1)

    @node_from(from_name='丽都周纪')
    @operation_node(name='领取积分')
    def claim_score(self, screen: MatLike = None) -> OperationRoundResult:
        if screen is None:
            screen = self.last_screenshot

        if self.ctx.controller.background_mode:
            if self.ctx.controller.background_ui.claim_weekly_score(screen):
                return self.round_wait('处理周纪任务', wait=0.5)
            return self.round_fail('无积分可领取')

        for i in range(3):
            area = self.ctx.screen_loader.get_area('丽都周纪', f'积分行-{i+1}')

            result = self.round_by_ocr_and_click(screen, '100', area=area,
                                                 lcs_percent=1,
                                                 color_range=[(250, 250, 250), (255, 255, 255)])

            if result.is_success:
                return self.round_wait(result.status, wait=0.5)

        return self.round_retry(result.status, wait=0.5)

    @node_from(from_name='领取积分', success=False)  # 没有100积分之后
    @node_notify(when=NotifyTiming.CURRENT_DONE)
    @operation_node(name='领取奖励', timeout_seconds=30)
    def confirm_schedule(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            result = self.round_by_find_and_click_area(self.last_screenshot, '快捷手册', '活跃度奖励-确认')
            if result.is_success:
                return self.round_wait('确认周纪奖励', wait=0.5)
            if not screen_utils.is_target_screen(self.ctx, self.last_screenshot, screen_name='丽都周纪'):
                return self.round_retry('等待周纪奖励页面', wait=0.5)
            result = self.round_by_find_area(self.last_screenshot, '丽都周纪', '手柄-可领取特赏')
            if not result.is_success:
                return self.round_success('无可领取特赏')
            self.ctx.controller.gamepad_ui_press('secondary')
            return self.round_wait('领取周纪奖励', wait=0.5)
        return self.round_by_click_area('丽都周纪', '领取奖励',
                                        success_wait=1, retry_wait=1)

    @node_from(from_name='领取奖励')
    @operation_node(name='完成后返回')
    def finish(self) -> OperationRoundResult:
        op = BackToNormalWorld(self.ctx)
        return self.round_by_op_result(op.execute())


def __debug():
    ctx = ZContext()
    ctx.init_by_config()
    app = RiduWeeklyApp(ctx)
    app.execute()


if __name__ == '__main__':
    __debug()
