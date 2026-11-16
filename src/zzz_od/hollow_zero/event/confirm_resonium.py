from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils.i18_utils import gt
from zzz_od.context.zzz_context import ZContext
from zzz_od.operation.zzz_operation import ZOperation


class ConfirmResonium(ZOperation):

    def __init__(self, ctx: ZContext):
        """
        在选择鸣徽的画面了 选择一个
        :param ctx:
        """
        ZOperation.__init__(
            self, ctx,
            op_name=gt('确认鸣徽', 'game')
        )

    @operation_node(name='选择', is_start_node=True)
    def choose_one(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            if all(self.round_by_find_area(self.last_screenshot, '零号空洞-事件', name).is_success
                   for name in ('手柄-战利品', '手柄-战利品确定')):
                self.ctx.controller.gamepad_ui_press('confirm')
                return self.round_success(wait=.5)
            if self.round_by_find_area(self.last_screenshot, '零号空洞-战斗', '鸣徽-确定').is_success:
                # 重构显示一张卡，催化对比显示同名两张卡；两种页面都只有一个已知鸣徽。
                area = self.ctx.screen_loader.get_area('零号空洞-事件', '手柄-鸣徽名称')
                labels = self.ctx.ocr_service.get_ocr_result_list(self.last_screenshot, rect=area.rect)
                cards = [card for label in labels
                         if (card := self.ctx.withered_domain.data_service.match_resonium_by_ocr_full(label.data)) is not None]
                if len(cards) in (1, 2) and all(card is cards[0] for card in cards):
                    self.ctx.controller.gamepad_ui_press('confirm')
                    return self.round_success(wait=.5)
            return self.round_retry('未确认鸣徽战利品页面', wait=.5)
        area = self.ctx.screen_loader.get_area('零号空洞-事件', '底部-选择列表')
        result = self.round_by_ocr_and_click(self.last_screenshot, '确认', area=area)
        if result.is_success:
            return self.round_success(wait=1)
        result = self.round_by_ocr_and_click(self.last_screenshot, '确定', area=area)
        if result.is_success:
            return self.round_success(wait=1)

        return self.round_retry(result.status, wait=1)
