import time

import cv2

from one_dragon.base.controller.background_input_error import BackgroundInputError
from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils.i18_utils import gt
from zzz_od.context.zzz_context import ZContext
from zzz_od.controller.gamepad_focus import find_focus_rects
from zzz_od.hollow_zero.event import resonium_utils
from zzz_od.operation.zzz_operation import ZOperation


class ChooseResonium(ZOperation):

    def __init__(self, ctx: ZContext):
        """
        在选择鸣徽的画面了 选择一个
        :param ctx:
        """
        ZOperation.__init__(
            self, ctx,
            op_name=gt('选择鸣徽', 'game')
        )

    @operation_node(name='选择', is_start_node=True)
    def choose_one(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            # 手柄仅在焦点卡下显示“选择”；读取所有卡牌名称，仍按原挑战配置排序。
            area = self.ctx.screen_loader.get_area('零号空洞-事件', '手柄-鸣徽名称').rect
            labels = self.ctx.ocr_service.get_ocr_result_list(self.last_screenshot, rect=area)
            cards = [(label, self.ctx.withered_domain.data_service.match_resonium_by_ocr_full(label.data))
                     for label in labels]
            expected_count = 1 if self.round_by_find_area(
                self.last_screenshot, '零号空洞-事件', '手柄-研究鸣徽',
            ).is_success else 3
            catalyst_rects = []
            if self.round_by_find_area(self.last_screenshot, '零号空洞-事件', '手柄-催化选择').is_success:
                # 催化只列出可强化的卡，可能不足三张；从完整彩色卡框计数，再核对全部名称。
                card_area = self.ctx.screen_loader.get_area('零号空洞-事件', '手柄-鸣徽卡片').rect
                crop = self.last_screenshot[card_area.y1:card_area.y2, card_area.x1:card_area.x2]
                mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_RGB2HSV), (0, 70, 85), (179, 255, 255))
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                catalyst_rects = [cv2.boundingRect(contour) for contour in contours
                                  if 250 <= cv2.boundingRect(contour)[2] <= 450
                                  and cv2.boundingRect(contour)[3] >= 400]
                expected_count = len(catalyst_rects)
                if expected_count not in (1, 2, 3):
                    return self.round_retry('未能确认催化卡片数量', wait=.5)
            if len(cards) != expected_count or any(
                card is None and label.data != gt('不可触碰之物', 'game') for label, card in cards
            ):
                # 战斗残留的 X 可能翻开焦点卡；确认背面名称与唯一焦点后翻回，再完整排序。
                back_area = self.ctx.screen_loader.get_area('零号空洞-事件', '手柄-鸣徽背面名称').rect
                back_labels = self.ctx.ocr_service.get_ocr_result_list(self.last_screenshot, rect=back_area)
                back_labels = [label for label in back_labels
                               if self.ctx.withered_domain.data_service.match_resonium_by_ocr_full(label.data) is not None]
                card_area = self.ctx.screen_loader.get_area('零号空洞-事件', '手柄-鸣徽卡片').rect
                focus = [rect for rect in find_focus_rects(self.last_screenshot, card_area) if rect.height >= 300]
                if len(back_labels) == 1 and len(focus) == 1:
                    center = back_labels[0].center
                    if focus[0].x1 <= center.x < focus[0].x2 and focus[0].y1 <= center.y < focus[0].y2:
                        self.ctx.controller.gamepad_ui_press('secondary')
                        return self.round_retry('等待鸣徽翻回正面', wait=.5)
            if len(cards) != expected_count:
                return self.round_retry('未能识别全部鸣徽名称', wait=.5)
            # 鸣徽厌性占用一个卡槽；明确识别禁用卡后才排除，不能忽略未知名称。
            cards = [(label, card) for label, card in cards if label.data != gt('不可触碰之物', 'game')]
            if not cards or any(card is None for _, card in cards):
                return self.round_retry('存在未识别的可选鸣徽', wait=.5)
            if catalyst_rects and any(sum(
                x <= label.center.x - card_area.x1 < x + width
                and y <= label.center.y - card_area.y1 < y + height for label, _ in cards
            ) != 1 for x, y, width, height in catalyst_rects):
                return self.round_retry('催化卡片与名称未一一对应', wait=.5)
            indexes = resonium_utils.choose_resonium_by_priority(
                [card for _, card in cards], self.ctx.withered_domain.challenge_config.resonium_priority,
            )
            if not indexes:
                return self.round_fail('鸣徽优先级无返回')
            self.ctx.controller.background_ui.select_hollow_resonium(self.last_screenshot, cards[indexes[0]][0].center)
            return self.round_success(wait=1)
        item_list = resonium_utils.get_to_choose_list(self.ctx, self.last_screenshot, '选择')
        if len(item_list) == 0:
            return self.round_retry(status='识别不到选项', wait=0.5)

        idx_list = resonium_utils.choose_resonium_by_priority([i.data for i in item_list],
                                                              self.ctx.withered_domain.challenge_config.resonium_priority)
        if len(idx_list) == 0:
            if len(item_list) >= 3:  # 如果都识别到了 那证明就是没有匹配到优先级
                return self.round_fail(status='优先级无返回')
            else:
                return self.round_retry(status='优先级无返回', wait=0.5)

        mr = item_list[idx_list[0]]
        self.ctx.controller.click(mr.center)
        time.sleep(0.1)
        return self.round_by_click_area('零号空洞-事件', '空白', success_wait=0.9)

    @node_from(from_name='选择', success=False)  # 防止识别有问题 兜底随便选一个
    @operation_node(name='兜底选择')
    def choose_default(self):
        if self.ctx.controller.background_mode:
            raise BackgroundInputError('无法确认鸣徽选项，未使用焦点卡替代配置优先级')
        area = self.ctx.screen_loader.get_area('零号空洞-事件', '底部-选择列表')
        return self.round_by_ocr_and_click(self.last_screenshot, '选择', area=area,
                                           success_wait=1, retry_wait=1,
                                           color_range=[(240, 240, 240), (255, 255, 255)])






def __debug():
    ctx = ZContext()
    ctx.init_by_config()
    ctx.run_context.start_running()
    ctx.init_ocr()
    op = ChooseResonium(ctx)
    op.execute()


if __name__ == '__main__':
    __debug()
