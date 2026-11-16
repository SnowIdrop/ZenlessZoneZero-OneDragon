import cv2
import numpy as np
from cv2.typing import MatLike
from typing import ClassVar

from one_dragon.base.controller.background_input_error import BackgroundInputError
from one_dragon.base.matcher.match_result import MatchResultList, MatchResult
from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils import cv2_utils, str_utils
from one_dragon.utils.i18_utils import gt
from one_dragon.utils.log_utils import log
from zzz_od.context.zzz_context import ZContext
from zzz_od.hollow_zero.event import hollow_event_utils, resonium_utils
from zzz_od.operation.zzz_operation import ZOperation


class BambooMerchant(ZOperation):

    STATUS_LEVEL_1: ClassVar[str] = '外层选择'
    STATUS_LEVEL_2_BUY: ClassVar[str] = '二级标题-鸣徽交易'
    STATUS_LEVEL_2_UPGRADE: ClassVar[str] = '二级标题-鸣徽催化'
    NOT_TO_BUY: ClassVar[str] = '不购买'

    def __init__(self, ctx: ZContext):
        """
        在邦布商人的画面了 尽量购买
        :param ctx:
        """
        ZOperation.__init__(
            self, ctx,
            op_name=gt('邦布商人', 'game')
        )

    @node_from(from_name='购买后确定')
    @operation_node(name='画面识别', is_start_node=True)
    def check_screen(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode and self.ctx.withered_domain.force_only_boss:
            # 速刷只经过商人格；若事件自动打开商店，识别层级后沿原返回流程离开。
            for name in ('二级标题', '手柄-外层选择'):
                rect = self.ctx.screen_loader.get_area('零号空洞-商店', name).rect
                labels = self.ctx.ocr_service.get_ocr_result_list(self.last_screenshot, rect=rect)
                if any(any(gt(text, 'game') in label.data for text in ('鸣徽交易', '鸣徽催化', '特价折扣', '血汗交易')) for label in labels):
                    return self.round_success(status=BambooMerchant.NOT_TO_BUY)
        area = self.ctx.screen_loader.get_area('零号空洞-商店', '二级标题')
        if self.ctx.controller.background_mode and self.round_by_ocr(
            self.last_screenshot, '血汗交易', area=area, lcs_percent=1,
        ).is_success:
            return self.round_success(status=BambooMerchant.NOT_TO_BUY)
        result = self.round_by_ocr(self.last_screenshot, '交易', area=area, lcs_percent=1)
        if result.is_success:
            return self.round_success(status=BambooMerchant.STATUS_LEVEL_2_BUY)

        result = self.round_by_ocr(self.last_screenshot, '特价折扣', area=area, lcs_percent=1)
        if result.is_success:
            return self.round_success(status=BambooMerchant.STATUS_LEVEL_2_BUY)

        result = self.round_by_ocr(self.last_screenshot, '催化', area=area, lcs_percent=1)
        if result.is_success:
            return self.round_success(status=BambooMerchant.STATUS_LEVEL_2_UPGRADE)

        result = self.round_by_ocr(self.last_screenshot, '血汗交易', area=area, lcs_percent=0.6)
        if result.is_success:
            return self.round_success(status=BambooMerchant.NOT_TO_BUY)

        area = self.ctx.screen_loader.get_area('零号空洞-事件', '底部-选择列表')
        result = self.round_by_ocr_and_click(self.last_screenshot, '确定', area=area)
        if result.is_success:
            return self.round_wait(wait=1)

        area = hollow_event_utils.get_event_text_area(self.ctx)
        result = self.round_by_ocr_and_click(self.last_screenshot, '进入商店', area=area, lcs_percent=0.6)
        if result.is_success:
            return self.round_wait(wait=1)

        result = self.round_by_ocr(self.last_screenshot, '血汗交易', area=area, lcs_percent=0.6)
        if result.is_success:
            return self.round_success(BambooMerchant.NOT_TO_BUY)

        result = self.round_by_ocr(self.last_screenshot, '鸣徽交易', area=area, lcs_percent=0.6)
        if result.is_success:
            return self.round_success(BambooMerchant.STATUS_LEVEL_1)

        result = self.round_by_ocr(self.last_screenshot, '特价折扣', area=area)
        if result.is_success:
            return self.round_success(BambooMerchant.STATUS_LEVEL_1)

        return self.round_retry('未知画面', wait=1)

    @node_from(from_name='画面识别', status=STATUS_LEVEL_1)
    @operation_node(name='鸣徽交易')
    def choose_buy(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            area = self.ctx.screen_loader.get_area('零号空洞-商店', '手柄-外层选择')
            labels = self.ctx.ocr_service.get_ocr_result_list(self.last_screenshot, rect=area.rect)
            targets = [label for label in labels if label.data in (gt('鸣徽交易', 'game'), gt('特价折扣', 'game'))]
            if len(targets) != 1:
                return self.round_retry('未确认商店交易选项', wait=.5)
            target = targets[0]
            crop = self.last_screenshot[target.y:target.y + target.h, target.x:target.x + target.w]
            mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_RGB2HSV), (25, 180, 160), (42, 255, 255))
            # 商店图标将黄色按钮分成两块，以目标文字的底色确认选择。
            if np.count_nonzero(mask) > mask.size * .4:
                self.ctx.controller.gamepad_ui_press('confirm')
                return self.round_success(BambooMerchant.STATUS_LEVEL_2_BUY, wait=.5)
            self.ctx.controller.gamepad_ui_press('up')
            return self.round_retry('等待交易选项选中', wait=.3)
        area = hollow_event_utils.get_event_text_area(self.ctx)

        result = self.round_by_ocr_and_click(self.last_screenshot, '鸣徽交易', area=area)
        if result.is_success:
            return self.round_success(BambooMerchant.STATUS_LEVEL_2_BUY, wait=1)

        result = self.round_by_ocr_and_click(self.last_screenshot, '特价折扣', area=area)
        if result.is_success:
            return self.round_success(BambooMerchant.STATUS_LEVEL_2_BUY, wait=1)

        return self.round_retry(status=result.status, wait=1)

    @node_from(from_name='画面识别', status=STATUS_LEVEL_2_BUY)
    @node_from(from_name='鸣徽交易')
    @operation_node(name='选择鸣徽')
    def choose_item(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            return self._choose_item_with_gamepad()
        price_ocr_result_map = self._ocr_price_area(self.last_screenshot)
        price_pos_list = [i.center for mrl in price_ocr_result_map.values() for i in mrl]

        desc_ocr_result_map = self._ocr_desc_area(self.last_screenshot)
        item_list = []
        pos_list = []
        # 只保留有价格的
        for ocr_result, mrl in desc_ocr_result_map.items():
            item = self.ctx.withered_domain.data_service.match_resonium_by_ocr_full(ocr_result)
            log.info('%s 匹配鸣徽 %s' % (ocr_result, item.name if item is not None else 'none'))
            if item is None:
                continue
            with_price: bool = False
            for price in price_pos_list:
                if price.y > mrl.max.center.y and price.y - mrl.max.center.y < 150:
                    with_price = True
                    break

            if not with_price:
                continue
            item_list.append(item)
            pos_list.append(mrl.max.center)

        if len(item_list) > 0:
            idx_list = resonium_utils.choose_resonium_by_priority(item_list, self.ctx.withered_domain.challenge_config.resonium_priority,
                                                                  only_priority=self.ctx.withered_domain.challenge_config.buy_only_priority)
            if len(idx_list) > 0:
                to_choose = pos_list[idx_list[0]]
            else:
                to_choose = None
        else:
            to_choose = None
            for price in price_pos_list:
                if to_choose is None or price.y > to_choose.y:
                    to_choose = price

        if to_choose is None:
            return self.round_success(BambooMerchant.NOT_TO_BUY, wait=1)
        else:
            self.ctx.controller.click(to_choose)
            return self.round_success(wait=1)

    def _choose_item_with_gamepad(self) -> OperationRoundResult:
        """按已有购买优先级选择可支付商品，A 提示确认焦点后直接购买。"""
        title = self.ctx.screen_loader.get_area('零号空洞-商店', '二级标题')
        titles = self.ctx.ocr_service.get_ocr_result_list(self.last_screenshot, rect=title.rect)
        if not any(label.data.startswith((gt('鸣徽交易', 'game'), gt('特价折扣', 'game'))) for label in titles):
            return self.round_retry('等待鸣徽交易商品列表', wait=.5)
        area = self.ctx.screen_loader.get_area('零号空洞-商店', '手柄-商品列表')
        labels = self.ctx.ocr_service.get_ocr_result_list(self.last_screenshot, rect=area.rect)
        items = []
        names = []
        for row in range(3):
            # 当前手柄商品页有三个竖排卡槽；完整识别每行后才能按优先级购买。
            row_top = area.y1 + row * 192
            row_names = [label for label in labels if row_top + 25 < label.center.y < row_top + 80
                         and label.x > area.x1 + 150]
            if len(row_names) != 1:
                return self.round_retry('商品名称未完整识别', wait=.5)
            label = row_names[0]
            prices = [price for price in labels if price.data.isdigit()
                      and 70 < price.center.y - label.center.y < 140]
            if len(prices) != 1:
                sold = [text for text in labels if text.data in (gt('售罄', 'game'), gt('已售出', 'game'))
                        and label.center.y < text.center.y < label.center.y + 140]
                if len(sold) == 1:
                    continue
                return self.round_retry('商品价格未完整识别', wait=.5)
            price = prices[0]
            crop = self.last_screenshot[price.y:price.y + price.h, price.x:price.x + price.w]
            hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
            yellow = cv2.inRange(hsv, (20, 150, 160), (42, 255, 255))
            # 买不起的价格是红色；不把它作为可购买商品或点击目标。
            if np.count_nonzero(yellow) < yellow.size * .1:
                red = cv2.inRange(hsv, (0, 150, 160), (10, 255, 255)) | cv2.inRange(hsv, (170, 150, 160), (180, 255, 255))
                if np.count_nonzero(red) > red.size * .1:
                    continue
                # 已购买卡仍保留名称和价格，但价格及卡面变灰；它不再是可购买商品。
                gray = cv2.inRange(hsv, (0, 0, 110), (180, 25, 220))
                if np.count_nonzero(gray) > gray.size * .1:
                    continue
                return self.round_retry('未确认商品是否可支付', wait=.5)
            item = self.ctx.withered_domain.data_service.match_resonium_by_ocr_full(label.data)
            if item is None:
                raise BackgroundInputError(f'未识别可购买鸣徽，无法按配置排序: {label.data}')
            items.append(item)
            names.append(label)
        order = resonium_utils.choose_resonium_by_priority(
            items, self.ctx.withered_domain.challenge_config.resonium_priority,
            only_priority=self.ctx.withered_domain.challenge_config.buy_only_priority,
        )
        if not order:
            return self.round_success(self.NOT_TO_BUY)
        prompts = [label for label in labels if label.data == 'A' and label.x > area.x2 - 120]
        if len(prompts) != 1:
            raise BackgroundInputError('未确认商店商品的 A 提示，未购买')
        target = names[order[0]]
        prompt = prompts[0]
        if 20 < prompt.center.y - target.center.y < 100:
            self.ctx.controller.gamepad_ui_press('confirm')
            return self.round_success('手柄已购买', wait=.5)
        self.ctx.controller.gamepad_ui_press('up' if target.center.y < prompt.center.y else 'down')
        return self.round_retry('等待目标商品选中', wait=.3)

    def _ocr_price_area(self, screen: MatLike) -> dict[str, MatchResultList]:
        area = self.ctx.screen_loader.get_area('零号空洞-商店', '商品价格区域')
        part = cv2_utils.crop_image_only(screen, area.rect)
        mask = cv2.inRange(part, (240, 140, 0), (255, 255, 50))
        mask = cv2_utils.dilate(mask, 2)

        to_ocr = cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB)
        # cv2_utils.show_image(to_ocr, wait=0)

        result_result_map = {}
        ocr_result_map = self.ctx.ocr.run_ocr(to_ocr)
        for ocr_result, mrl in ocr_result_map.items():
            digit = str_utils.get_positive_digits(ocr_result, None)
            if digit is None:  # 忽略没有数字的
                continue
            mrl.add_offset(area.left_top)
            result_result_map[ocr_result] = mrl

        if len(result_result_map) == 0:
            # 没有识别的情况 可能是价格为0识别不到 额外再每个价格格子识别一次
            for i in range(2, 4):
                for j in range(1, i+1):
                    area = self.ctx.screen_loader.get_area('零号空洞-商店', f'商品价格-{i}-{j}')
                    part = cv2_utils.crop_image_only(screen, area.rect)
                    mask = cv2.inRange(part, (240, 140, 0), (255, 255, 50))
                    mask = cv2_utils.dilate(mask, 2)
                    to_ocr = cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB)
                    # cv2_utils.show_image(to_ocr, wait=0)
                    # 底层onnx的ocr 使用 run_ocr 会对只有一个0的情况识别不到 只能用这个方法
                    ocr_result = self.ctx.ocr.run_ocr_single_line(to_ocr)
                    for special_char in ['.', '。', 'o', 'O']:  # 0 有可能被识别成其它字符 特殊处理
                        ocr_result = ocr_result.replace(special_char, '0')
                    digit = str_utils.get_positive_digits(ocr_result, None)
                    if digit is None:
                        continue
                    # 构造返回结果
                    digit_str = str(digit)
                    if digit_str not in result_result_map:
                        result_result_map[digit_str] = MatchResultList(only_best=False)
                    result_result_map[digit_str].append(
                        MatchResult(1, area.left_top.x, area.left_top.y, area.width, area.height,
                                    data=digit_str)
                    )

        return result_result_map

    def _ocr_desc_area(self, screen: MatLike) -> dict[str, MatchResultList]:
        area = self.ctx.screen_loader.get_area('零号空洞-商店', '商品描述区域')
        part = cv2_utils.crop_image_only(screen, area.rect)
        ocr_result_map = self.ctx.ocr.crop_and_run_ocr(screen, area.rect)
        for mrl in ocr_result_map.values():
            mrl.add_offset(area.left_top)

        return ocr_result_map

    @node_from(from_name='选择鸣徽')
    @operation_node(name='购买')
    def buy(self) -> OperationRoundResult:
        return self.round_by_find_and_click_area(self.last_screenshot, '零号空洞-商店', '商品购买区域')

    @node_from(from_name='购买')
    @node_from(from_name='选择鸣徽', status='手柄已购买')
    @operation_node(name='购买后确定')
    def confirm(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            result = self.round_by_find_area(self.last_screenshot, '零号空洞-事件', '手柄-战利品')
            if not result.is_success:
                return self.round_retry('等待购买战利品', wait=.5)
            result = self.round_by_find_area(self.last_screenshot, '零号空洞-事件', '手柄-战利品确定')
            if result.is_success:
                self.ctx.controller.gamepad_ui_press('confirm')
                return self.round_success(wait=.5)
            return self.round_retry('未确认战利品按钮', wait=.5)
        return self.round_by_find_and_click_area(self.last_screenshot, '零号空洞-商店', '购买后确定',
                                                 success_wait=1, retry_wait=1)

    @node_from(from_name='画面识别', status=STATUS_LEVEL_2_UPGRADE)
    @operation_node(name='鸣徽催化')
    def upgrade_resonium(self) -> OperationRoundResult:
        return self.round_success()

    @node_from(from_name='画面识别', status=NOT_TO_BUY)
    @node_from(from_name='选择鸣徽', status=NOT_TO_BUY)
    @node_from(from_name='鸣徽催化')
    @node_from(from_name='鸣徽交易', success=False)  # 在第一层找到选项 就退出
    @operation_node(name='返回', timeout_seconds=15)
    def back(self) -> OperationRoundResult:
        if self.ctx.controller.background_mode:
            area = self.ctx.screen_loader.get_area('零号空洞-商店', '二级标题')
            titles = self.ctx.ocr_service.get_ocr_result_list(self.last_screenshot, rect=area.rect)
            if any(any(gt(text, 'game') in label.data for text in ('交易', '催化', '特价折扣')) for label in titles):
                self.ctx.controller.gamepad_ui_press('back')
                return self.round_wait('返回商店外层', wait=.5)
            area = self.ctx.screen_loader.get_area('零号空洞-商店', '手柄-外层选择')
            labels = self.ctx.ocr_service.get_ocr_result_list(self.last_screenshot, rect=area.rect)
            if any(any(gt(text, 'game') in label.data for text in ('鸣徽交易', '鸣徽催化', '特价折扣', '血汗交易')) for label in labels):
                self.ctx.controller.gamepad_ui_press('back')
                return self.round_wait('等待离开商店', wait=.5)
            if hollow_event_utils.check_in_hollow(self.ctx, self.last_screenshot) is not None:
                current_map = self.ctx.withered_domain.map_service.cal_map_by_screen(self.last_screenshot, self.last_screenshot_time)
                if current_map is not None and current_map.is_valid_map:
                    return self.round_success('已返回电视地图')
            return self.round_retry('未确认商店返回层级', wait=.5)
        result1 = self.round_by_find_and_click_area(self.last_screenshot, '零号空洞-商店', '右上角-返回',
                                                    success_wait=1.5, retry_wait=1)

        if not result1.is_success:
            return self.round_retry(status=result1.status)

        return self.round_by_find_and_click_area(self.last_screenshot, '零号空洞-商店', '右上角-返回',
                                                 success_wait=1, retry_wait=1)


def __debug_check_screen():
    ctx = ZContext()
    ctx.init_by_config()
    ctx.init_ocr()
    op = BambooMerchant(ctx)
    from one_dragon.utils import os_utils
    import os
    screen = cv2_utils.read_image(os.path.join(
        os_utils.get_path_under_work_dir('.debug', 'devtools', 'screen', 'hollow_zero_merchant'),
        '_1725071431457.png'
    ))
    from one_dragon.utils import debug_utils
    screen = debug_utils.get_debug_image('1')
    print(op._ocr_price_area(screen))
    area = hollow_event_utils.get_event_text_area(op.ctx)
    print(op.round_by_ocr(screen, '鸣徽交易', area=area, lcs_percent=0.6).status)


if __name__ == '__main__':
    __debug_check_screen()
