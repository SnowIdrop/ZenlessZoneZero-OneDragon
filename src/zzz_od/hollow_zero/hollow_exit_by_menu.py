from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils.i18_utils import gt
from zzz_od.context.zzz_context import ZContext
from zzz_od.controller.gamepad_focus import find_focus_rects
from zzz_od.operation.zzz_operation import ZOperation


class HollowExitByMenu(ZOperation):

    def __init__(self, ctx: ZContext):
        """
        需要在空洞中 右下角有显示背包时使用
        如果有对话框的话会卡住
        :param ctx:
        """
        ZOperation.__init__(
            self, ctx,
            op_name=gt('离开空洞', 'game')
        )

    @operation_node(name='点击菜单', is_start_node=True)
    def click_menu(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            if all(self.round_by_find_area(self.last_screenshot, '零号空洞-事件', name).is_success
                   for name in ('手柄-菜单暂离', '手柄-菜单放弃')):
                return self.round_success()
            if not self.round_by_find_area(self.last_screenshot, '零号空洞-事件', '背包').is_success:
                return self.round_retry('未确认电视探索画面', wait=1)
            self.ctx.controller.gamepad_ui_press('start')
            return self.round_retry('等待空洞菜单', wait=1)
        result = self.round_by_find_area(self.last_screenshot, '零号空洞-事件', '放弃')
        if result.is_success:  # 点击到出现了放弃按钮为止
            return self.round_success()

        result = self.round_by_click_area('零号空洞-事件', '菜单')
        if result.is_success:
            return self.round_wait(wait=1)

        return self.round_retry(result.status, wait=1)

    @node_from(from_name='点击菜单')
    @operation_node(name='点击离开')
    def click_leave(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            if not all(self.round_by_find_area(self.last_screenshot, '零号空洞-事件', name).is_success
                       for name in ('手柄-菜单暂离', '手柄-菜单放弃')):
                return self.round_retry('未确认空洞菜单', wait=1)
            self.ctx.controller.gamepad_ui_press('tertiary')
            return self.round_success(wait=1)
        return self.round_by_find_and_click_area(self.last_screenshot, '零号空洞-事件', '放弃',
                                                 success_wait=1, retry_wait=1)

    @node_from(from_name='点击离开')
    @operation_node(name='确认离开')
    def confirm_leave(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            if not self.round_by_find_area(self.last_screenshot, '零号空洞-事件', '手柄-放弃提示').is_success:
                return self.round_retry('未确认放弃探索提示', wait=1)
            target = self.ctx.screen_loader.get_area('零号空洞-事件', '放弃-确认').center
            region = self.ctx.screen_loader.get_area('画面-通用', '手柄-确认选择').rect
            focus = find_focus_rects(self.last_screenshot, region)
            if len(focus) != 1:
                return self.round_retry('未确认放弃按钮焦点', wait=.5)
            if not (focus[0].x1 <= target.x < focus[0].x2 and focus[0].y1 <= target.y < focus[0].y2):
                self.ctx.controller.gamepad_ui_press('right')
                return self.round_retry('选择放弃确认', wait=.5)
            self.ctx.controller.gamepad_ui_press('confirm')
            return self.round_success(wait=1)
        return self.round_by_find_and_click_area(self.last_screenshot, '零号空洞-事件', '放弃-确认',
                                                 success_wait=1, retry_wait=1)

    @node_from(from_name='确认离开')
    @operation_node(name='点击完成', node_max_retry_times=20)
    def click_finish(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            if all(self.round_by_find_area(self.last_screenshot, '零号空洞-事件', name).is_success
                   for name in ('手柄-放弃结算', '手柄-通关完成')):
                self.ctx.controller.gamepad_ui_press('back')
                return self.round_retry('等待关闭退出结算', wait=1)
            if all(self.round_by_find_area(self.last_screenshot, '零号空洞-入口', name).is_success
                   for name in ('手柄-资质考核', '手柄-施工废墟')):
                return self.round_success('已返回空洞入口')
            return self.round_retry('等待退出空洞', wait=1)
        # 这个按钮刚出现的时候可以按不到 需要重复按它
        result = self.round_by_find_and_click_area(self.last_screenshot, '零号空洞-事件', '通关-完成')
        if result.is_success:
            return self.round_wait(wait=1)

        result = self.round_by_find_area(self.last_screenshot, '零号空洞-入口', '街区')
        if result.is_success:  # 点击直到返回显示街区为止
            return self.round_success()

        return self.round_retry(wait=1)
