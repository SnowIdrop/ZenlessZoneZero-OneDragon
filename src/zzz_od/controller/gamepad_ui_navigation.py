from __future__ import annotations

import difflib
import time
from typing import TYPE_CHECKING

import cv2
import numpy as np

from one_dragon.base.controller.background_input_error import BackgroundInputError
from one_dragon.base.geometry.point import Point
from one_dragon.base.geometry.rectangle import Rect
from one_dragon.base.matcher.match_result import MatchResult
from one_dragon.base.screen import screen_utils
from one_dragon.base.screen.screen_utils import FindAreaResultEnum
from one_dragon.utils import str_utils
from one_dragon.utils.i18_utils import gt
from zzz_od.controller.gamepad_focus import find_focus_rects

if TYPE_CHECKING:
    from cv2.typing import MatLike

    from zzz_od.context.zzz_context import ZContext
    from zzz_od.game_data.compendium import CompendiumMissionType


class GamepadUiNavigation:
    """将已确认的界面坐标目标转换为有截图反馈的手柄选择。"""

    def __init__(self, ctx: ZContext) -> None:
        self.ctx: ZContext = ctx

    def _is_map(self, image: MatLike) -> bool:
        """通过多个主区域名称区分地图与其他带返回键的页面。"""
        area = self.ctx.screen_loader.get_area('地图', '主区域名称')
        labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=area.rect)
        names = [gt(name, 'game') for name in self.ctx.map_service.area_name_map]
        return sum(str_utils.find_best_match_by_difflib(label.data, names) is not None for label in labels) >= 3

    def _focus(self, image: MatLike, region: Rect, min_height: int = 28, min_value: int = 160,
               allow_top_protrusion: bool = False) -> Rect:
        """导航区域内必须只有一个选中框，避免选择装饰或其他分组。"""
        matches = [rect for rect in find_focus_rects(image, region, min_value, allow_top_protrusion)
                   if rect.height >= min_height]
        if len(matches) != 1:
            raise BackgroundInputError(f'无法确认手柄焦点，导航区域内识别到 {len(matches)} 个选中框')
        return matches[0]

    def _navigate(
        self, image: MatLike, target: Point, region: Rect, *, confirm: bool = True,
        min_focus_height: int = 28, text_match_threshold: float = 1.0,
        label_rows: tuple[tuple[int, int], ...] = (),
        merge_text_lines: bool = False,
        ignore_text_punctuation: bool = False,
        min_focus_value: int = 160,
        allow_top_protrusion: bool = False,
    ) -> bool:
        """逐步移动到可见目标；每次按键后必须先看到焦点变化。"""
        def read_labels(frame: MatLike) -> list[MatchResult]:
            labels = self.ctx.ocr_service.get_ocr_result_list(frame, rect=region)
            labels = [label for label in labels if not label_rows
                      or any(top <= label.center.y < bottom for top, bottom in label_rows)]
            if ignore_text_punctuation:
                # 鸣徽括号在选中前后可能被识别为不同符号，名称和分类仍须完全一致。
                labels = [MatchResult(label.confidence, label.x, label.y, label.w, label.h,
                                      data=''.join(char for char in label.data if char.isalnum()))
                          for label in labels]
            if not merge_text_lines:
                return labels
            # 事件选项变为黑字后，OCR 可能将逗号两侧的文本由两块合为一块。
            lines: list[MatchResult] = []
            for label in sorted(labels, key=lambda item: (item.center.y, item.x)):
                previous = lines[-1] if lines else None
                if (previous is not None and abs(previous.center.y - label.center.y) < min(previous.h, label.h) / 2
                        and 0 <= max(label.x, previous.x) - min(label.x + label.w, previous.x + previous.w) < 80):
                    left = min(previous.x, label.x)
                    previous.w = max(label.x + label.w, previous.x + previous.w) - left
                    previous.data = previous.data + label.data if previous.x < label.x else label.data + previous.data
                    previous.x = left
                else:
                    lines.append(MatchResult(label.confidence, label.x, label.y, label.w, label.h, data=label.data))
            for line in lines:
                line.data = ''.join(char for char in line.data if char.isalnum())
            return lines

        labels = read_labels(image)
        target_labels = [label.data for label in labels
                         if label.x <= target.x <= label.x + label.w
                         and label.y <= target.y <= label.y + label.h]
        if len(target_labels) != 1:
            raise BackgroundInputError('未能确认待选择目标的文字，未发送确认键')
        target_text = target_labels[0]
        for _ in range(24):
            # 卡片名称先出现，选中边框随后完成动画；只在实际识别到焦点后发送输入。
            deadline = time.monotonic() + 2
            while not any(rect.height >= min_focus_height for rect in find_focus_rects(
                    image, region, min_focus_value, allow_top_protrusion)):
                if time.monotonic() >= deadline:
                    raise BackgroundInputError('等待手柄焦点出现超时')
                time.sleep(.08)
                image = self.ctx.controller.get_screenshot()
            # 列表滚动和选中动画会改变坐标，始终按原目标文字重新定位。
            labels = read_labels(image)
            targets = [label for label in labels if label.data == target_text]
            if not targets and text_match_threshold < 1:
                # 卡牌移动时偶有单字 OCR 波动，仍要求相似名称唯一。
                targets = [label for label in labels if difflib.SequenceMatcher(
                    None, label.data, target_text,
                ).ratio() >= text_match_threshold]
            if len(targets) != 1:
                raise BackgroundInputError(f'导航过程中目标消失或不唯一: {target_text}')
            target = targets[0].center
            focus = self._focus(image, region, min_focus_height, min_focus_value, allow_top_protrusion)
            if focus.x1 <= target.x < focus.x2 and focus.y1 <= target.y < focus.y2:
                if confirm:
                    self.ctx.controller.gamepad_ui_press('confirm')
                return True
            if target.x < focus.x1:
                direction = 'left'
            elif target.x >= focus.x2:
                direction = 'right'
            elif target.y < focus.y1:
                direction = 'up'
            else:
                direction = 'down'
            self.ctx.controller.gamepad_ui_press(direction)
            # 游戏截图中的选中框变化是继续导航的条件，等待时长只用于判定失败。
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                image = self.ctx.controller.get_screenshot()
                matches = [rect for rect in find_focus_rects(image, region, min_focus_value, allow_top_protrusion)
                           if rect.height >= min_focus_height]
                if (len(matches) == 1
                        and not (focus.x1 <= matches[0].center.x < focus.x2
                                 and focus.y1 <= matches[0].center.y < focus.y2)):
                    break
                time.sleep(0.08)
            else:
                raise BackgroundInputError(f'手柄焦点没有响应方向键: {direction}')
        raise BackgroundInputError('手柄界面导航超过允许步数')

    def select_hollow_event_option(self, image: MatLike, target: Point) -> bool:
        """沿用事件配置选择选项，以黄色焦点确认实际选中的文本。"""
        if screen_utils.find_area(self.ctx, image, '零号空洞-事件', '背包') != FindAreaResultEnum.TRUE:
            raise BackgroundInputError('未确认零号空洞事件画面')
        region = self.ctx.screen_loader.get_area('零号空洞-事件', '手柄-事件选项').rect
        return self._navigate(image, target, region, merge_text_lines=True)

    def click(self, target: Point, press_time: float = 0) -> bool:
        """只处理已验证的页面、返回按钮和确认按钮。"""
        image = self.ctx.controller.get_screenshot()
        hollow_result = self._click_hollow(image, target)
        if hollow_result is not None:
            return hollow_result
        if screen_utils.find_area(self.ctx, image, '恶名狩猎', '手柄-周期挑战标题') == FindAreaResultEnum.TRUE:
            close = self.ctx.screen_loader.get_area('恶名狩猎', '手柄-周期挑战关闭').rect
            if close.x1 <= target.x < close.x2 and close.y1 <= target.y < close.y2:
                self.ctx.controller.gamepad_ui_press('back')
                return True
        hunt_entry = self.ctx.screen_loader.get_area('恶名狩猎', '手柄-周期挑战入口').rect
        if (hunt_entry.x1 <= target.x < hunt_entry.x2 and hunt_entry.y1 <= target.y < hunt_entry.y2
                and screen_utils.find_area(self.ctx, image, '恶名狩猎', '手柄-周期挑战入口') == FindAreaResultEnum.TRUE):
            region = Rect(500, 300, 1650, 930)
            if not find_focus_rects(image, region):
                # 分类选中后先进入右侧列表；下一帧确认焦点后才能打开奖励页。
                self.ctx.controller.gamepad_ui_press('confirm')
                return True
            return self._navigate(image, target, region)
        if screen_utils.find_area(self.ctx, image, '影像店营业', '昨日账本') == FindAreaResultEnum.TRUE:
            close = self.ctx.screen_loader.get_area('影像店营业', '按钮-关闭').rect
            if close.x1 <= target.x < close.x2 and close.y1 <= target.y < close.y2:
                self.ctx.controller.gamepad_ui_press('back')
                return True
        if screen_utils.find_area(self.ctx, image, '影像店营业', '选择宣传员') == FindAreaResultEnum.TRUE:
            region = self.ctx.screen_loader.get_area('影像店营业', '手柄-宣传员列表').rect
            if region.x1 <= target.x < region.x2 and region.y1 <= target.y < region.y2:
                labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=region)
                labels = [label for label in labels if label.data != 'EMPTY']
                if not labels:
                    raise BackgroundInputError('未识别到宣传员名称')
                label = min(labels, key=lambda item: (item.center.x-target.x)**2 + (item.center.y-target.y)**2)
                return self._navigate(image, label.center, region, confirm=False, min_focus_height=150)
            confirm = self.ctx.screen_loader.get_area('影像店营业', '确认').rect
            if confirm.x1 <= target.x < confirm.x2 and confirm.y1 <= target.y < confirm.y2:
                self.ctx.controller.gamepad_ui_press('confirm')
                return True
        if screen_utils.find_area(self.ctx, image, '影像店营业', '经营状况') == FindAreaResultEnum.TRUE:
            region = self.ctx.screen_loader.get_area('影像店营业', '手柄-经营页签').rect
            if region.x1 <= target.x < region.x2 and region.y1 <= target.y < region.y2:
                return self._select_tab(image, gt('经营状况', 'game'), region, ('经营状况', '无人咨询', '咨询中'))
            for index, name in enumerate(('宣传员入口', '录像带入口')):
                area = self.ctx.screen_loader.get_area('影像店营业', name).rect
                if area.x1 <= target.x < area.x2 and area.y1 <= target.y < area.y2:
                    return self._select_business_slot(image, index)
            area = self.ctx.screen_loader.get_area('影像店营业', '手柄-开始营业').rect
            if area.x1 <= target.x < area.x2 and area.y1 <= target.y < area.y2:
                self.ctx.controller.gamepad_ui_press('secondary')
                return True
        if screen_utils.find_area(self.ctx, image, '影像店营业', '上架筛选') == FindAreaResultEnum.TRUE:
            area = self.ctx.screen_loader.get_area('影像店营业', '手柄-推荐上架').rect
            if area.x1 <= target.x < area.x2 and area.y1 <= target.y < area.y2:
                self.ctx.controller.gamepad_ui_press('secondary')
                return True
        if screen_utils.is_target_screen(self.ctx, image, screen_name='丽都周纪'):
            reward = self.ctx.screen_loader.get_area('丽都周纪', '领取奖励').center
            if target.tuple() == reward.tuple():
                self.ctx.controller.gamepad_ui_press('secondary')
                return True
        if all(screen_utils.find_area(self.ctx, image, '丽都城募', name) == FindAreaResultEnum.TRUE
               for name in ('等级回馈', '成长任务')):
            for name in ('等级回馈', '成长任务'):
                area = self.ctx.screen_loader.get_area('丽都城募', name).rect
                if area.x1 <= target.x < area.x2 and area.y1 <= target.y < area.y2:
                    region = self.ctx.screen_loader.get_area('丽都城募', '手柄-页签').rect
                    return self._select_tab(image, gt(name, 'game'), region,
                                            ('等级回馈', '成长任务', '城募赠礼'))
            for name in ('任务-全部领取', '等级-全部领取'):
                area = self.ctx.screen_loader.get_area('丽都城募', name).rect
                if (area.x1 <= target.x < area.x2 and area.y1 <= target.y < area.y2
                        and screen_utils.find_area(self.ctx, image, '丽都城募', name) == FindAreaResultEnum.TRUE):
                    self.ctx.controller.gamepad_ui_press('secondary')
                    return True
        if screen_utils.find_area(self.ctx, image, '咖啡店', '点单') == FindAreaResultEnum.TRUE:
            order = self.ctx.screen_loader.get_area('咖啡店', '点单').rect
            if order.x1 <= target.x < order.x2 and order.y1 <= target.y < order.y2:
                self.ctx.controller.gamepad_ui_press('confirm')
                return True
            coffee_list = self.ctx.screen_loader.get_area('咖啡店', '咖啡列表').rect
            if coffee_list.x1 <= target.x < coffee_list.x2 and coffee_list.y1 <= target.y < coffee_list.y2:
                return self._select_coffee(image, target)
        back = self.ctx.screen_loader.get_area('菜单', '返回')
        if back.rect.x1 <= target.x < back.rect.x2 and back.rect.y1 <= target.y < back.rect.y2:
            if screen_utils.find_area(self.ctx, image, '菜单', '返回') == FindAreaResultEnum.TRUE:
                self.ctx.controller.gamepad_ui_press('back')
                return True
            # 返回按钮在转场期间不可见，让调用方重新识别，不向未知页面发送按键。
            return False

        confirm = self.ctx.screen_loader.get_area('画面-通用', '手柄-确认选择').rect
        for screen_name, area_name in (
            ('地图', '确认'), ('快捷手册', '传送确认'), ('咖啡店', '不可贪杯确认'),
            ('咖啡店', '电量确认'), ('咖啡店', '对话框确认'), ('邮件', '确认'),
            ('快捷手册', '活跃度奖励-确认'), ('丽都城募', '按钮-确认'),
            ('影像店营业', '开始营业-确认'), ('影像店营业', '营业后确认'),
        ):
            area = self.ctx.screen_loader.get_area(screen_name, area_name).rect
            if (area.x1 <= target.x < area.x2 and area.y1 <= target.y < area.y2
                    and screen_utils.find_area(self.ctx, image, screen_name, area_name) == FindAreaResultEnum.TRUE):
                return self._navigate(image, target, confirm)

        tabs = self.ctx.screen_loader.get_area('快捷手册', 'TAB列表').rect
        labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=tabs)
        tab_names = ('目标', '日常', '训练', '作战', '战术')
        labels = [label for label in labels if label.data in {gt(name, 'game') for name in tab_names}]
        if len(labels) >= 3:
            for label in labels:
                if label.x <= target.x < label.x + label.w and label.y <= target.y < label.y + label.h:
                    return self._select_tab(image, label.data, tabs, tab_names)
            close = self.ctx.screen_loader.get_area('快捷手册-日常', '按钮-关闭').rect
            if close.x1 <= target.x < close.x2 and close.y1 <= target.y < close.y2:
                self.ctx.controller.gamepad_ui_press('back')
                return True

        if screen_utils.is_target_screen(self.ctx, image, screen_name='快捷手册-日常'):
            weekly = self.ctx.screen_loader.get_area('丽都周纪', '丽都周纪').rect
            if weekly.x1 <= target.x < weekly.x2 and weekly.y1 <= target.y < weekly.y2:
                region = self.ctx.screen_loader.get_area('快捷手册', '手柄-日常任务').rect
                return self._navigate(image, target, region)
            area = self.ctx.screen_loader.get_area('快捷手册', '今日最大活跃度').rect
            if area.x1 <= target.x < area.x2 and area.y1 <= target.y < area.y2:
                self.ctx.controller.gamepad_ui_press('secondary')
                return True

        if screen_utils.is_target_screen(self.ctx, image, screen_name='菜单'):
            region = self.ctx.screen_loader.get_area('菜单', '手柄-底部选择').rect
            if region.x1 <= target.x < region.x2 and region.y1 <= target.y < region.y2:
                return self._navigate(image, target, region)

        if self._is_map(image):
            return self._click_map(image, target)

        if screen_utils.is_target_screen(self.ctx, image, screen_name='邮件'):
            area = self.ctx.screen_loader.get_area('邮件', '全部领取')
            if area.rect.x1 <= target.x < area.rect.x2 and area.rect.y1 <= target.y < area.rect.y2:
                self.ctx.controller.gamepad_ui_press('secondary')
                return True

        raise BackgroundInputError(f'当前页面尚未适配纯手柄选择，目标: {target}')

    def _click_hollow(self, image: MatLike, target: Point) -> bool | None:
        """零号空洞入口、调查战略与出战准备使用各自的手柄入口。"""
        if screen_utils.find_area(self.ctx, image, '零号空洞-事件', '背包') == FindAreaResultEnum.TRUE:
            bottom = self.ctx.screen_loader.get_area('零号空洞-事件', '底部-选择列表').rect
            if bottom.x1 <= target.x < bottom.x2 and bottom.y1 <= target.y < bottom.y2:
                labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=bottom)
                if {gt(name, 'game') for name in ('回复生命值', '获得齿轮硬币', '降低压力值')} <= {label.data for label in labels}:
                    return self._navigate(image, target, bottom)
            region = self.ctx.screen_loader.get_area('零号空洞-事件', '手柄-事件选项').rect
            if region.x1 <= target.x < region.x2 and region.y1 <= target.y < region.y2:
                return self.select_hollow_event_option(image, target)
        if screen_utils.find_area(self.ctx, image, '迷失之地-大世界', '手柄-对话继续') == FindAreaResultEnum.TRUE:
            dialog = self.ctx.screen_loader.get_area('迷失之地-大世界', '手柄-对话框').rect
            if dialog.x1 <= target.x < dialog.x2 and dialog.y1 <= target.y < dialog.y2:
                self.ctx.controller.gamepad_ui_press('confirm')
                return True
        if self.is_withered_area_map(image):
            return self._select_withered_area(image, target)
        if screen_utils.find_area(self.ctx, image, '零号空洞-入口', '手柄-关键敌情') == FindAreaResultEnum.TRUE:
            region = self.ctx.screen_loader.get_area('零号空洞-入口', '手柄-关卡列表').rect
            if region.x1 <= target.x < region.x2 and region.y1 <= target.y < region.y2:
                return self._navigate(image, target, region, confirm=False, min_focus_height=90)
            next_step = self.ctx.screen_loader.get_area('零号空洞-入口', '下一步').rect
            if next_step.x1 <= target.x < next_step.x2 and next_step.y1 <= target.y < next_step.y2:
                if screen_utils.find_area(self.ctx, image, '零号空洞-入口', '下一步') != FindAreaResultEnum.TRUE:
                    return False
                self.ctx.controller.gamepad_ui_press('start')
                return True
        if all(screen_utils.find_area(self.ctx, image, '零号空洞-入口', name) == FindAreaResultEnum.TRUE
               for name in ('分支-深层调查', '分支-迷失之地', '分支-枯萎之都')):
            for index, name in enumerate(('分支-迷失之地', '分支-枯萎之都')):
                area = self.ctx.screen_loader.get_area('零号空洞-入口', name).rect
                if area.x1 <= target.x < area.x2 and area.y1 <= target.y < area.y2:
                    region = self.ctx.screen_loader.get_area('零号空洞-入口', '手柄-分支按键').rect
                    previous: int | None = None
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        crop = image[region.y1:region.y2, region.x1:region.x2]
                        mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_RGB2HSV), (40, 150, 100), (95, 255, 255))
                        halves = np.array_split(mask, 2, axis=1)
                        selected = [idx for idx, half in enumerate(halves) if np.count_nonzero(half) > 30]
                        if selected == [index]:
                            self.ctx.controller.gamepad_ui_press('confirm')
                            return True
                        if len(selected) == 1 and selected[0] != previous:
                            self.ctx.controller.gamepad_ui_press('left' if index == 0 else 'right')
                            previous = selected[0]
                        time.sleep(.08)
                        image = self.ctx.controller.get_screenshot()
                    raise BackgroundInputError('未能确认零号空洞分支下方的 A 按键位置')
        if screen_utils.find_area(self.ctx, image, '迷失之地-入口', '更新-标题') == FindAreaResultEnum.TRUE:
            area = self.ctx.screen_loader.get_area('迷失之地-入口', '按钮-更新弹窗-关闭').rect
            if area.x1 <= target.x < area.x2 and area.y1 <= target.y < area.y2:
                self.ctx.controller.gamepad_ui_press('back')
                return True
        if screen_utils.find_area(self.ctx, image, '迷失之地-入口', '手柄-调查战略标题') == FindAreaResultEnum.TRUE:
            area = self.ctx.screen_loader.get_area('迷失之地-入口', '手柄-调查战略确定').rect
            if area.x1 <= target.x < area.x2 and area.y1 <= target.y < area.y2:
                self.ctx.controller.gamepad_ui_press('confirm')
                return True
            region = self.ctx.screen_loader.get_area('迷失之地-入口', '手柄-调查战略列表').rect
            if region.x1 <= target.x < region.x2 and region.y1 <= target.y < region.y2:
                self.select_hollow_strategy_target(image, target)
                return True
        standard = screen_utils.is_target_screen(self.ctx, image, screen_name='迷失之地-入口-常规')
        periodic = screen_utils.is_target_screen(self.ctx, image, screen_name='迷失之地-入口-周期')
        if standard or periodic:
            for name, action in (('按钮-常规', 'next_tab'), ('按钮-周期', 'previous_tab')):
                area = self.ctx.screen_loader.get_area('迷失之地-入口', name).rect
                if area.x1 <= target.x < area.x2 and area.y1 <= target.y < area.y2:
                    self.ctx.controller.gamepad_ui_press(action)
                    return True
            if standard:
                region = self.ctx.screen_loader.get_area('迷失之地-入口', '手柄-常规选择').rect
                if region.x1 <= target.x < region.x2 and region.y1 <= target.y < region.y2:
                    return self._navigate(image, target, region, min_focus_height=150)
        if screen_utils.is_target_screen(self.ctx, image, screen_name='迷失之地-战线肃清'):
            strategy = self.ctx.screen_loader.get_area('迷失之地-战线肃清', '按钮-调查战略').rect
            if strategy.x1 <= target.x < strategy.x2 and strategy.y1 <= target.y < strategy.y2:
                self.ctx.controller.gamepad_ui_press('tertiary')
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    image = self.ctx.controller.get_screenshot()
                    if screen_utils.find_area(self.ctx, image, '迷失之地-入口', '手柄-调查战略标题') == FindAreaResultEnum.TRUE:
                        return True
                    time.sleep(.08)
                raise BackgroundInputError('调查战略列表未响应打开按键')
            region = self.ctx.screen_loader.get_area('迷失之地-入口', '手柄-周期增益').rect
            if region.x1 <= target.x < region.x2 and region.y1 <= target.y < region.y2:
                if not find_focus_rects(image, region):
                    self.ctx.controller.gamepad_ui_press('confirm')
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        image = self.ctx.controller.get_screenshot()
                        if find_focus_rects(image, region):
                            break
                        time.sleep(.08)
                    else:
                        raise BackgroundInputError('未能进入周期增益选择')
                labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=region)
                rows = [self.ctx.screen_loader.get_area('迷失之地-战线肃清', f'周期增益-{name}').rect
                        for name in ('第一个', '第二个', '第三个')]
                row = next((rect for rect in rows if rect.y1 <= target.y < rect.y2), None)
                labels = [label for label in labels if row is not None and row.y1 <= label.center.y < row.y2]
                if not labels:
                    raise BackgroundInputError('未识别到目标行的周期增益说明')
                label = min(labels, key=lambda item: abs(item.center.y - target.y))
                return self._navigate(image, label.center, region)
        for name in ('按钮-下一步', '按钮-出战'):
            area = self.ctx.screen_loader.get_area('通用-出战', name).rect
            if (area.x1 <= target.x < area.x2 and area.y1 <= target.y < area.y2
                    and screen_utils.find_area(self.ctx, image, '通用-出战', name) == FindAreaResultEnum.TRUE):
                self.ctx.controller.gamepad_ui_press('start')
                return True
        return None

    def advance_lost_void_tutorial(self, image: MatLike, previous_text: str | None) -> str | None:
        """同一教学说明只确认一次，提示换页后才允许再次按 A。"""
        icon = self.ctx.screen_loader.get_area('迷失之地-武备选择', '手柄-教学标识').rect
        crop = image[icon.y1:icon.y2, icon.x1:icon.x2]
        mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_RGB2HSV), (90, 100, 100), (130, 255, 255))
        if cv2.countNonZero(mask) < 50:
            return None
        region = self.ctx.screen_loader.get_area('迷失之地-武备选择', '手柄-教学说明').rect
        labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=region)
        text = ''.join(char for label in sorted(labels, key=lambda item: item.x)
                       for char in label.data if char.isalnum())
        if sum('\u4e00' <= char <= '\u9fff' for char in text) < 4:
            # Fairy 标识仍在，说明是教学文字换页，不能进入下层的选牌流程。
            return previous_text or ''
        if (text != previous_text
                and screen_utils.find_area(self.ctx, image, '迷失之地-武备选择', '手柄-教学确认')
                == FindAreaResultEnum.TRUE):
            self.ctx.controller.gamepad_ui_press('confirm')
            return text
        if (text == '打开详情可查看具体效果' and text != previous_text
                and screen_utils.find_area(self.ctx, image, '迷失之地-武备选择', '手柄-教学详情按键')
                == FindAreaResultEnum.TRUE):
            self.ctx.controller.gamepad_ui_press('details')
            return text
        return previous_text or ''

    def is_lost_void_selection(self, image: MatLike) -> bool:
        """手柄版没有键盘 TAB 图标，用完整选择标题与确定按钮共同识别。"""
        region = self.ctx.screen_loader.get_area('迷失之地-通用选择', '区域-标题').rect
        labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=region)
        title = ''.join(char for label in sorted(labels, key=lambda item: item.x)
                        for char in label.data if char.isalnum())
        titles = ('请选择1枚鸣徽', '请选择一枚鸣徽', '请选择2枚鸣徽', '请选择两枚鸣徽',
                  '请选择1项', '请选择2项', '请选择1张卡牌', '请选择1个武备',
                  '请选择战术棱镜方案强化的方向', '获得武备', '武备已升级', '获得战利品')
        return title in titles and screen_utils.find_area(
            self.ctx, image, '迷失之地-通用选择', '按钮-确定') == FindAreaResultEnum.TRUE

    def is_withered_area_map(self, image: MatLike) -> bool:
        """未结束的探索会锁住其他区域，使用底部入口与仍可见的区域名称辨认。"""
        if all(screen_utils.find_area(self.ctx, image, '零号空洞-入口', name) == FindAreaResultEnum.TRUE
               for name in ('手柄-资质考核', '手柄-施工废墟')):
            return True
        if not all(screen_utils.find_area(self.ctx, image, '零号空洞-入口', name) == FindAreaResultEnum.TRUE
                   for name in ('手柄-探索收集', '手柄-作战机略')):
            return False
        region = self.ctx.screen_loader.get_area('零号空洞-入口', '手柄-枯萎区域').rect
        names = {gt(name, 'game') for name in ('资质考核', '旧都列车', '施工废墟', '巨厦遗骸', '枯败花圃')}
        return any(label.data in names for label in self.ctx.ocr_service.get_ocr_result_list(image, rect=region))

    def resume_withered_exploration(self, image: MatLike, mission_name: str) -> bool:
        """只继续弹窗中明确标示的配置关卡，不接手其他未结束的探索。"""
        region = self.ctx.screen_loader.get_area('零号空洞-入口', '手柄-继续探索提示').rect
        labels = sorted(self.ctx.ocr_service.get_ocr_result_list(image, rect=region), key=lambda label: label.x)
        text = ''.join(char for label in labels for char in label.data if char.isalnum())
        prefix = gt('当前正在处理', 'game')
        suffix = gt('是否继续', 'game')
        if not text.startswith(prefix) or not text.endswith(suffix):
            return False
        expected = ''.join(char for char in gt(mission_name, 'game') if char.isalnum())
        if text[len(prefix):-len(suffix)] != expected:
            raise BackgroundInputError('未结束的空洞探索与配置关卡不同，未确认继续')
        if screen_utils.find_area(self.ctx, image, '零号空洞-入口', '继续-确认') != FindAreaResultEnum.TRUE:
            raise BackgroundInputError('已识别继续探索提示，但未确认继续按钮')
        confirm = self.ctx.screen_loader.get_area('零号空洞-入口', '继续-确认').rect
        focus = self._focus(image, self.ctx.screen_loader.get_area('画面-通用', '手柄-确认选择').rect)
        if not (focus.x1 <= confirm.center.x < focus.x2 and focus.y1 <= confirm.center.y < focus.y2):
            raise BackgroundInputError('继续探索的确认按钮未获得焦点')
        self.ctx.controller.gamepad_ui_press('confirm')
        return True

    def _select_withered_area(self, image: MatLike, target: Point) -> bool | None:
        """枯萎之都各区域以名称下方的绿色 A 图标表示当前焦点。"""
        region = self.ctx.screen_loader.get_area('零号空洞-入口', '手柄-枯萎区域').rect
        names = {gt(name, 'game') for name in ('资质考核', '旧都列车', '施工废墟', '巨厦遗骸', '枯败花圃')}
        labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=region)
        targets = [label for label in labels if label.data in names
                   and label.x <= target.x < label.x + label.w and label.y <= target.y < label.y + label.h]
        if not targets:
            return None
        if len(targets) != 1:
            raise BackgroundInputError('枯萎之都目标区域名称不唯一')
        target_name = targets[0].data
        previous: str | None = None
        deadline = time.monotonic() + 2
        for _ in range(60):
            labels = [label for label in self.ctx.ocr_service.get_ocr_result_list(image, rect=region)
                      if label.data in names]
            targets = [label for label in labels if label.data == target_name]
            selected = []
            for label in labels:
                # 通关圆点紧贴名称，只检测更下方的 A 提示，排除通关进度的绿色圆点。
                crop = image[label.y + 70:label.y + 150, label.center.x - 25:label.center.x + 25]
                mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_RGB2HSV), (60, 150, 100), (95, 255, 255))
                if np.count_nonzero(mask) > 25:
                    selected.append(label)
            if len(selected) == 1 and len(targets) == 1:
                current, destination = selected[0], targets[0]
                if current.data == target_name:
                    self.ctx.controller.gamepad_ui_press('confirm')
                    return True
                if current.data != previous:
                    dx, dy = destination.center.x - current.center.x, destination.center.y - current.center.y
                    direction = ('right' if dx > 0 else 'left') if abs(dx) > abs(dy) else ('down' if dy > 0 else 'up')
                    self.ctx.controller.gamepad_ui_press(direction)
                    previous = current.data
                    deadline = time.monotonic() + 2
            if time.monotonic() >= deadline:
                raise BackgroundInputError(f'枯萎之都区域未响应手柄导航: {target_name}')
            time.sleep(.08)
            image = self.ctx.controller.get_screenshot()
        raise BackgroundInputError(f'未能选择枯萎之都区域: {target_name}')

    def select_hollow_resonium(self, image: MatLike, target: Point) -> bool:
        """按已经识别的鸣徽名称导航，选择前仍确认目标处在唯一卡牌焦点内。"""
        region = self.ctx.screen_loader.get_area('零号空洞-事件', '手柄-鸣徽卡片').rect
        return self._navigate(image, target, region, min_focus_height=300, ignore_text_punctuation=True)

    def select_hollow_strategy_target(self, image: MatLike, target: Point) -> None:
        """将追新检测的原截图坐标转为名称，再用新截图按该名称选择。"""
        region = self.ctx.screen_loader.get_area('迷失之地-入口', '手柄-调查战略列表').rect
        labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=region)
        labels = [label for label in labels if label.data.endswith(gt('战略', 'game'))]
        if target.y < 400:
            # 等级圆标在本张卡牌的右上角；相邻卡牌间距超过此范围。
            labels = [label for label in labels if 0 < target.x - label.center.x < 250]
        else:
            labels = [label for label in labels if label.x <= target.x < label.x + label.w
                      and label.y <= target.y < label.y + label.h]
        if len(labels) != 1:
            raise BackgroundInputError('未能将调查战略目标唯一关联到本张卡牌名称')
        self.select_hollow_strategy(labels[0].data)

    def select_hollow_strategy(self, name: str) -> None:
        """按配置名称选择调查战略，避免跨截图的旧坐标改变目标身份。"""
        image = self.ctx.controller.get_screenshot()
        if screen_utils.find_area(self.ctx, image, '迷失之地-入口', '手柄-调查战略标题') != FindAreaResultEnum.TRUE:
            raise BackgroundInputError('未确认调查战略列表')
        region = self.ctx.screen_loader.get_area('迷失之地-入口', '手柄-调查战略列表').rect
        labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=region)
        labels = [label for label in labels if difflib.SequenceMatcher(None, label.data, gt(name, 'game')).ratio() >= .8]
        if len(labels) != 1:
            raise BackgroundInputError(f'配置的调查战略不在当前可识别卡牌中: {name}')
        self._navigate(image, labels[0].center, region, confirm=False, min_focus_height=200,
                       text_match_threshold=.8)

    def select_compendium_category(self, image: MatLike, name: str) -> bool:
        """分类用蓝色底色识别；关卡列表中先返回分类，再按上下键选择。"""
        region = self.ctx.screen_loader.get_area('快捷手册', '分类列表').rect
        buttons = self.ctx.screen_loader.get_area('快捷手册', '手柄-前往选择').rect
        previous: tuple[str, bool] | None = None
        deadline = time.monotonic() + 2
        for _ in range(80):
            labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=region)
            targets = [label for label in labels if str_utils.find_by_lcs(gt(name, 'game'), label.data, percent=0.8)]
            selected = []
            for label in labels:
                # 文字左侧的底色避开粗体字和 NEW 标记，不以字形占比判断分类。
                crop = image[label.y:label.y + label.h, max(region.x1, label.x - 16):label.x - 5]
                if crop.size == 0:
                    continue
                mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_RGB2HSV), (100, 90, 80), (130, 255, 255))
                if np.count_nonzero(mask) > mask.size * 0.4:
                    selected.append(label)
            if len(selected) > 1:
                # 特训目标的副标题也在蓝底内；连续蓝色背景中的多行文字只取最上方分类名。
                top = min(selected, key=lambda label: label.y)
                strip = image[top.y:max(label.y + label.h for label in selected),
                              max(region.x1, top.x - 16):top.x - 5]
                if strip.size:
                    blue = cv2.inRange(cv2.cvtColor(strip, cv2.COLOR_RGB2HSV), (100, 90, 80), (130, 255, 255))
                    if np.all(np.count_nonzero(blue, axis=1) > blue.shape[1] * .4):
                        selected = [top]
            if len(selected) == 1 and len(targets) == 1:
                current = selected[0]
                if current.data == targets[0].data:
                    return True
                in_missions = bool(find_focus_rects(image, buttons))
                state = (current.data, in_missions)
                if state != previous:
                    self.ctx.controller.gamepad_ui_press(
                        'back' if in_missions else ('up' if targets[0].y < current.y else 'down'),
                    )
                    previous = state
                    deadline = time.monotonic() + 2
            if time.monotonic() >= deadline:
                raise BackgroundInputError(f'未能选择快捷手册分类: {name}')
            time.sleep(0.08)
            image = self.ctx.controller.get_screenshot()
        raise BackgroundInputError(f'快捷手册分类导航超过允许步数: {name}')

    def select_compendium_mission(self, image: MatLike, mission: CompendiumMissionType) -> bool:
        """进入关卡列表，以高亮前往按钮上方的名称确认目标，滚动后重新定位。"""
        names = [gt(name, 'game') for name in [mission.mission_type_name, *mission.alias_list]]
        category = self.ctx.screen_loader.get_area('快捷手册', '分类列表').rect
        region = self.ctx.screen_loader.get_area('快捷手册', '副本列表').rect
        buttons = self.ctx.screen_loader.get_area('快捷手册', '手柄-前往选择').rect
        previous: str | None = None
        visited: set[str] = set()
        deadline = time.monotonic() + 2
        for _ in range(120):
            # 分类和页签仍须属于本次目标；无焦点不能单独证明可以按 A。
            category_labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=category)
            category_labels = [label for label in category_labels if str_utils.find_by_lcs(
                gt(mission.category.category_name, 'game'), label.data, percent=0.8,
            )]
            valid_category = False
            if len(category_labels) == 1:
                label = category_labels[0]
                crop = image[label.y:label.y + label.h, max(category.x1, label.x - 16):label.x - 5]
                if crop.size:
                    mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_RGB2HSV), (100, 90, 80), (130, 255, 255))
                    valid_category = np.count_nonzero(mask) > mask.size * 0.4
            if not valid_category or not screen_utils.is_target_screen(
                self.ctx, image, screen_name=f'快捷手册-{mission.category.tab.tab_name}',
            ):
                raise BackgroundInputError('快捷手册页签或分类与传送目标不一致')
            labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=region)
            focuses = find_focus_rects(image, buttons)
            if not focuses and previous is None:
                go_labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=buttons)
                if not any(label.data == gt('前往', 'game') for label in go_labels):
                    raise BackgroundInputError('未确认快捷手册关卡列表，未发送进入按键')
                self.ctx.controller.gamepad_ui_press('confirm')
                previous = '进入关卡列表'
                deadline = time.monotonic() + 2
            elif len(focuses) == 1:
                focus = focuses[0]
                above = [label for label in labels if 0 < focus.center.y - label.center.y < 180]
                if above:
                    current = max(above, key=lambda label: label.y)
                    matches = difflib.get_close_matches(current.data, names, n=1, cutoff=0.8)
                    if matches:
                        self.ctx.controller.gamepad_ui_press('confirm')
                        return True
                    if current.data != previous:
                        # 列表到末尾会绕回首项；重复访问说明目标在本轮可用列表中不存在。
                        if current.data in visited:
                            raise BackgroundInputError(f'快捷手册可用关卡中未找到目标: {names[0]}')
                        visited.add(current.data)
                        targets = [label for label in labels if difflib.get_close_matches(label.data, names, n=1, cutoff=0.8)]
                        self.ctx.controller.gamepad_ui_press(
                            'up' if len(targets) == 1 and targets[0].y < current.y else 'down',
                        )
                        previous = current.data
                        deadline = time.monotonic() + 2
            if time.monotonic() >= deadline:
                raise BackgroundInputError(f'快捷手册关卡未响应导航或目标不可见: {names[0]}')
            time.sleep(0.08)
            image = self.ctx.controller.get_screenshot()
        raise BackgroundInputError(f'快捷手册关卡导航超过允许步数: {names[0]}')

    def _select_business_slot(self, image: MatLike, index: int) -> bool:
        """经营页四个固定卡槽无文字，以卡槽位置和焦点反馈选择入口。"""
        region = self.ctx.screen_loader.get_area('影像店营业', '手柄-经营卡片').rect
        for _ in range(4):
            focus = self._focus(image, region, 150)
            selected = min(range(4), key=lambda idx: abs(focus.center.x - (region.x1 + region.width * (idx + 0.5) / 4)))
            if selected == index:
                self.ctx.controller.gamepad_ui_press('confirm')
                return True
            self.ctx.controller.gamepad_ui_press('left' if selected > index else 'right')
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                image = self.ctx.controller.get_screenshot()
                matches = [rect for rect in find_focus_rects(image, region) if rect.height >= 150]
                if len(matches) == 1 and matches[0].center.tuple() != focus.center.tuple():
                    break
                time.sleep(0.08)
            else:
                raise BackgroundInputError('经营卡槽未响应手柄方向键')
        raise BackgroundInputError('未能选择经营卡槽')

    def _select_tab(self, image: MatLike, name: str, region: Rect, names: tuple[str, ...]) -> bool:
        """肩键页签按文字的黄色底色定位，看到选中页变化后才继续。"""
        allowed = {gt(item, 'game') for item in names}
        previous: str | None = None
        deadline = time.monotonic() + 2
        for _ in range(80):
            labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=region)
            labels = [label for label in labels if label.data in allowed]
            selected = []
            for label in labels:
                crop = image[label.y:label.y + label.h, label.x:label.x + label.w]
                mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_RGB2HSV), (24, 180, 160), (42, 255, 255))
                if np.count_nonzero(mask) > mask.size * 0.4:
                    selected.append(label)
            target = [label for label in labels if label.data == name]
            if len(selected) == 1 and len(target) == 1:
                current = selected[0]
                if current.data == name:
                    return True
                if current.data != previous:
                    self.ctx.controller.gamepad_ui_press(
                        'previous_tab' if target[0].center.x < current.center.x else 'next_tab',
                    )
                    previous = current.data
                    deadline = time.monotonic() + 2
            if time.monotonic() >= deadline:
                raise BackgroundInputError(f'页签未响应手柄肩键: {name}')
            time.sleep(0.08)
            image = self.ctx.controller.get_screenshot()
        raise BackgroundInputError(f'未能切换到目标页签: {name}')

    def claim_weekly_score(self, image: MatLike) -> bool:
        """周纪只选择底部积分条亮起的任务，按任务名称导航后领取。"""
        if not screen_utils.is_target_screen(self.ctx, image, screen_name='丽都周纪'):
            raise BackgroundInputError('未确认丽都周纪页面，未发送领取输入')
        if screen_utils.find_area(self.ctx, image, '丽都周纪', '引导-下一步') == FindAreaResultEnum.TRUE:
            self.ctx.controller.gamepad_ui_press('confirm')
            return True
        grid = self.ctx.screen_loader.get_area('丽都周纪', '手柄-任务网格').rect
        width, height = grid.width // 3, grid.height // 3
        for row in range(3):
            for col in range(3):
                x, y = grid.x1 + col * width, grid.y1 + row * height
                strip = image[y + height - 45:y + height - 20, x + 30:x + width - 30]
                mask = cv2.inRange(cv2.cvtColor(strip, cv2.COLOR_RGB2HSV), (25, 150, 140), (42, 255, 255))
                if np.count_nonzero(mask) < mask.size * 0.4:
                    continue
                labels = self.ctx.ocr_service.get_ocr_result_list(
                    image, rect=Rect(x + 20, y + 40, x + width - 20, y + 100),
                )
                labels = [label for label in labels if not label.data.replace('/', '').isdigit()]
                if len(labels) != 1:
                    raise BackgroundInputError('未能确认可领取积分的周纪任务名称')
                return self._navigate(image, labels[0].center, grid, min_focus_height=150)
        return False

    def _select_coffee(self, image: MatLike, target: Point) -> bool:
        """用左右键选择咖啡，以右侧预览名称验证，选择阶段不发送点单键。"""
        area = self.ctx.screen_loader.get_area('咖啡店', '咖啡列表').rect
        preview = self.ctx.screen_loader.get_area('咖啡店', '手柄-咖啡预览').rect
        labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=area)
        coffees = [label for label in labels if difflib.get_close_matches(
            label.data, self.ctx.compendium_service.name_2_coffee, n=1, cutoff=0.8,
        )]
        if not coffees:
            raise BackgroundInputError('未识别到可选择的咖啡名称')
        selected = min(coffees, key=lambda label: abs(label.center.x - target.x))
        names = [label.data for label in coffees]
        for _ in range(len(coffees) + 1):
            preview_labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=preview)
            matches = difflib.get_close_matches(''.join(label.data for label in preview_labels), names, n=1, cutoff=0.8)
            if not matches:
                raise BackgroundInputError('未识别到当前咖啡预览，未提交点单')
            current = next(label for label in coffees if label.data == matches[0])
            if current.data == selected.data:
                return True
            self.ctx.controller.gamepad_ui_press('left' if selected.center.x < current.center.x else 'right')
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                image = self.ctx.controller.get_screenshot()
                changed = self.ctx.ocr_service.get_ocr_result_list(image, rect=preview)
                next_names = difflib.get_close_matches(''.join(label.data for label in changed), names, n=1, cutoff=0.8)
                if next_names and next_names[0] != current.data:
                    break
                time.sleep(0.08)
            else:
                raise BackgroundInputError('咖啡预览没有响应手柄方向键')
        raise BackgroundInputError('未能选择目标咖啡')

    def _click_map(self, image: MatLike, target: Point) -> bool:
        """区分区域网格与传送点列表，进入对应分组后选择目标。"""
        grid = self.ctx.screen_loader.get_area('地图', '主区域名称').rect
        points = self.ctx.screen_loader.get_area('地图', '手柄-传送点选择').rect
        points_active = len(find_focus_rects(image, points)) == 1
        target_is_point = target.y >= points.y1
        if points_active != target_is_point:
            self.ctx.controller.gamepad_ui_press('confirm' if target_is_point else 'back')
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                image = self.ctx.controller.get_screenshot()
                if (len(find_focus_rects(image, points)) == 1) == target_is_point:
                    break
                time.sleep(0.08)
            else:
                raise BackgroundInputError('地图未切换到目标选择分组')
        if target_is_point:
            return self._navigate(image, target, points)
        # 同一地点的插画 Logo 和右下名称可能同时被 OCR 识别；只用每行底部的正式名称。
        rows = tuple((grid.y1 + grid.height * (idx + 1) // 3 - 70,
                      grid.y1 + grid.height * (idx + 1) // 3) for idx in range(3))
        labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=grid)
        originals = [label for label in labels if label.x <= target.x < label.x + label.w
                     and label.y <= target.y < label.y + label.h]
        if len(originals) != 1:
            raise BackgroundInputError('未能确认地图目标名称')
        captions = [label for label in labels if label.data == originals[0].data
                    and any(top <= label.center.y < bottom for top, bottom in rows)]
        if len(captions) != 1:
            raise BackgroundInputError('未能确认地图卡片下方的唯一名称')
        return self._navigate(image, captions[0].center, grid, label_rows=rows)

    def drag(self, start: Point, end: Point) -> None:
        """地图翻页使用方向键，目标是否出现仍由调用方重新识别。"""
        image = self.ctx.controller.get_screenshot()
        if not self._is_map(image) or abs(end.x - start.x) <= abs(end.y - start.y):
            raise BackgroundInputError('当前页面尚未适配纯手柄拖拽')
        points = self.ctx.screen_loader.get_area('地图', '手柄-传送点选择').rect
        points_active = len(find_focus_rects(image, points)) == 1
        if points_active != (start.y >= points.y1):
            raise BackgroundInputError('地图翻页目标与当前手柄选择分组不一致')
        region = points if points_active else self.ctx.screen_loader.get_area('地图', '主区域名称').rect
        labels = self.ctx.ocr_service.get_ocr_result_list(image, rect=region)
        previous_names = {label.data for label in labels}
        for _ in range(12):
            focus = self._focus(image, region)
            self.ctx.controller.gamepad_ui_press('right' if end.x < start.x else 'left')
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                image = self.ctx.controller.get_screenshot()
                matches = find_focus_rects(image, region)
                if len(matches) == 1 and matches[0].center.tuple() != focus.center.tuple():
                    break
                names = {label.data for label in self.ctx.ocr_service.get_ocr_result_list(image, rect=region)}
                if names != previous_names:
                    return
                time.sleep(0.08)
            else:
                # 焦点和内容均未变化，已经到边界，交给地图操作处理反向或目标不存在。
                return
            names = {label.data for label in self.ctx.ocr_service.get_ocr_result_list(image, rect=region)}
            if names != previous_names:
                return
        raise BackgroundInputError('地图方向键未能完成翻页')
