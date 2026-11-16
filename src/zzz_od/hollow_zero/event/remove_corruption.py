from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils.i18_utils import gt
from zzz_od.context.zzz_context import ZContext
from zzz_od.operation.zzz_operation import ZOperation


class RemoveCorruption(ZOperation):

    def __init__(self, ctx: ZContext):
        """
        在选择鸣徽的画面了 选择一个
        :param ctx:
        """
        ZOperation.__init__(
            self, ctx,
            op_name=gt('清除侵蚀症状', 'game')
        )

    @operation_node(name='选择', is_start_node=True)
    def choose_one(self) -> OperationRoundResult:
        area = self.ctx.screen_loader.get_area('零号空洞-事件', '底部-清除列表')
        if self.ctx.controller.background_mode:
            region = self.ctx.screen_loader.get_area('零号空洞-事件', '手柄-侵蚀卡片').rect
            focus = self.ctx.controller.background_ui._focus(self.last_screenshot, region, min_height=250)
            labels = self.ctx.ocr_service.get_ocr_result_list(self.last_screenshot, rect=area.rect)
            # 此操作没有侵蚀优先级，确认当前高亮卡下确有清除按钮即可选择。
            if not any(label.data == gt('清除', 'game') and focus.x1 <= label.center.x < focus.x2 for label in labels):
                return self.round_retry('未确认高亮侵蚀的清除按钮', wait=.5)
            self.ctx.controller.gamepad_ui_press('confirm')
            return self.round_success(wait=1)
        return self.round_by_ocr_and_click(self.last_screenshot, '清除', area=area,
                                           color_range=[(240, 240, 240), (255, 255, 255)],
                                           crop_first=False,
                                           success_wait=1, retry_wait=1)
