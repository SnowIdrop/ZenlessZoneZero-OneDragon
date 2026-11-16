from one_dragon.base.geometry.rectangle import Rect
from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils.i18_utils import gt
from zzz_od.context.zzz_context import ZContext
from zzz_od.operation.zzz_operation import ZOperation


class RestartInBattle(ZOperation):

    def __init__(self, ctx: ZContext):
        """
        在战斗画面 尝试退出
        :param ctx: 上下文
        """
        ZOperation.__init__(self, ctx, op_name=gt('战斗中-重新开始'))
        self.gamepad_menu_sent: bool = False
        self.gamepad_restart_sent: bool = False
        self.gamepad_confirm_sent: bool = False

    @operation_node(name='画面识别', is_start_node=True, node_max_retry_times=10)
    def check_screen(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            if self.round_by_find_area(self.last_screenshot, '战斗-菜单', '手柄-重开提示').is_success:
                return self.round_success('重开确认')
            if all(self.round_by_find_area(self.last_screenshot, '战斗-菜单', name).is_success
                   for name in ('按钮-战况', '手柄-重开按键', '手柄-重新开始')):
                return self.round_success()
            if (not self.gamepad_menu_sent
                    and self.ctx.auto_battle_context.is_normal_attack_btn_available(self.last_screenshot)):
                self.ctx.controller.gamepad_ui_press('start')
                self.gamepad_menu_sent = True
            return self.round_retry('等待手柄战斗菜单', wait=.5)
        # 点击直到出现 [退出战斗] 按钮
        result = self.round_by_find_area(self.last_screenshot, '战斗-菜单', '按钮-退出战斗')
        if result.is_success:
            return self.round_success(wait=1)  # 稍微等一下让按钮可按
        result = self.round_by_click_area('战斗画面', '菜单')
        return self.round_retry(result.status, wait=1)

    @node_from(from_name='画面识别')
    @operation_node(name='点击退出战斗')
    def click_exit_battle(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            if self.round_by_find_area(self.last_screenshot, '战斗-菜单', '手柄-重开提示').is_success:
                return self.round_success()
            if not self.gamepad_restart_sent and all(
                    self.round_by_find_area(self.last_screenshot, '战斗-菜单', name).is_success
                    for name in ('按钮-战况', '手柄-重开按键', '手柄-重新开始')):
                self.ctx.controller.gamepad_ui_press('secondary')
                self.gamepad_restart_sent = True
            return self.round_retry('等待重新开始确认框', wait=.5)
        return self.round_by_find_and_click_area(self.last_screenshot, '战斗-菜单', '按钮-重新开始',
                                                 until_find_all=[('战斗-菜单', '按钮-退出战斗-确认')],
                                                 success_wait=1, retry_wait=1)

    @node_from(from_name='点击退出战斗')
    @node_from(from_name='画面识别', status='重开确认')
    @operation_node(name='点击确认', node_max_retry_times=60)
    def click_confirm(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            if self.gamepad_confirm_sent:
                if self.ctx.auto_battle_context.is_normal_attack_btn_available(self.last_screenshot):
                    return self.round_success('已返回战斗场景')
                return self.round_retry('等待重新开始加载完成', wait=.5)
            if all(self.round_by_find_area(self.last_screenshot, '战斗-菜单', name).is_success
                   for name in ('手柄-重开提示', '手柄-确认按键')):
                area = self.ctx.screen_loader.get_area('战斗-菜单', '按钮-退出战斗-确认')
                self.ctx.controller.background_ui._navigate(
                    self.last_screenshot, area.center, Rect(650,570,1290,680))
                self.gamepad_confirm_sent = True
            return self.round_retry('等待重新开始确认生效', wait=.5)
        return self.round_by_find_and_click_area(screen_name='战斗-菜单', area_name='按钮-退出战斗-确认',
                                                 until_not_find_all=[('战斗-菜单', '按钮-退出战斗-确认')],
                                                 success_wait=1, retry_wait=1)

def __debug():
    """
    调试用
    """
    ctx = ZContext()
    ctx.init()
    ctx.init_ocr()
    ctx.run_context.start_running()

    op = RestartInBattle(ctx)
    op.execute()


if __name__ == "__main__":
    __debug()
