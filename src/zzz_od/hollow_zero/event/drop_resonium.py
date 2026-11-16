import time

from one_dragon.base.controller.background_input_error import BackgroundInputError
from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils.i18_utils import gt
from zzz_od.context.zzz_context import ZContext
from zzz_od.controller.gamepad_focus import find_focus_rects
from zzz_od.hollow_zero.event import resonium_utils
from zzz_od.operation.zzz_operation import ZOperation


class DropResoniumBase(ZOperation):

    def __init__(self, ctx: ZContext, drop_cn: str):
        """
        在选择鸣徽的画面了 选择一个
        :param ctx:
        """
        ZOperation.__init__(
            self, ctx,
            op_name=gt('丢弃鸣徽', 'game')
        )

        self.drop_cn: str = drop_cn
        self._background_discard_sent: bool = False

    @operation_node(name='选择', is_start_node=True, timeout_seconds=15)
    def choose_one(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            return self._choose_background()
        item_list = resonium_utils.get_to_choose_list(self.ctx, self.last_screenshot, self.drop_cn)
        if len(item_list) == 0:
            return self.round_retry(status='识别不到选项', wait=0.5)

        idx_list = resonium_utils.choose_resonium_by_priority([i.data for i in item_list],
                                                              self.ctx.withered_domain.challenge_config.resonium_priority)
        if len(idx_list) == 0:
            return self.round_retry(status='优先级无返回', wait=0.5)

        mr = item_list[idx_list[-1]]  # 丢弃优先级最低的
        self.ctx.controller.click(mr.center)
        time.sleep(0.1)
        return self.round_by_click_area('零号空洞-事件', '空白', success_wait=0.9)

    def _choose_background(self) -> OperationRoundResult:
        """确认公平交易的批量丢弃预览；其他需要选卡的变体不能套用。"""
        image = self.last_screenshot
        if self._background_discard_sent:
            if all(self.round_by_find_area(image, '零号空洞-事件', name).is_success
                   for name in ('手柄-战利品', '手柄-战利品确定')):
                return self.round_success('已确认交易战利品')
            return self.round_wait('等待丢弃结果', wait=.5)
        if self.drop_cn != '丢弃' or not self.round_by_find_area(
            image, '零号空洞-事件', '手柄-丢弃冗余',
        ).is_success:
            raise BackgroundInputError('当前丢弃鸣徽页面尚未适配纯手柄操作')
        area = self.ctx.screen_loader.get_area('零号空洞-事件', '底部-选择列表').rect
        labels = [label for label in self.ctx.ocr_service.get_ocr_result_list(image, rect=area)
                  if label.data == gt(self.drop_cn, 'game')]
        focus = find_focus_rects(image, area)
        if len(labels) != 1:
            return self.round_retry('未识别到唯一丢弃按钮', wait=.5)
        target = labels[0].center
        if len(focus) != 1 or not (focus[0].x1 <= target.x < focus[0].x2 and focus[0].y1 <= target.y < focus[0].y2):
            self.ctx.controller.gamepad_ui_press('down')
            return self.round_wait('等待丢弃按钮获得焦点', wait=.5)
        self.ctx.controller.gamepad_ui_press('confirm')
        self._background_discard_sent = True
        return self.round_wait('等待丢弃结果', wait=.5)

    @node_from(from_name='选择', success=False)  # 防止识别有问题 兜底随便选一个
    @operation_node(name='兜底选择')
    def choose_default(self):
        if self.ctx.controller.background_mode:
            raise BackgroundInputError('无法确认丢弃鸣徽，未使用默认卡替代配置优先级')
        area = self.ctx.screen_loader.get_area('零号空洞-事件', '底部-选择列表')
        return self.round_by_ocr_and_click(self.last_screenshot, self.drop_cn, area=area,
                                           success_wait=1, retry_wait=1)


class DropResonium(DropResoniumBase):

    def __init__(self, ctx: ZContext):
        DropResoniumBase.__init__(self, ctx, '丢弃')


class DropResonium2(DropResoniumBase):

    def __init__(self, ctx: ZContext):
        DropResoniumBase.__init__(self, ctx, '抵押欠款')
