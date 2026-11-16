---
screen_name: 零号空洞-入口
appears_in: [枯萎之都]
last_updated: 2026-11-15
source_image: screens/零号空洞-入口/withered-type-right.webp
---

# 枯萎之都手柄入口

玩法见 [枯萎之都](../gameplay/withered_domain.md)。旧版区域仍存于 `hollow_zero_entry.yml`；本节只记录实拍手柄子态。

## 入口和流转

快捷手册「作战／周期征讨／迷失之地」传送后，在深层调查分支页选择枯萎之都。区域图显示资质考核、旧都列车、施工废墟、巨厦遗骸、枯败花圃；不显示旧版「街区」文字。

区域图 → 方向键选区域、A 进入 → 右侧关卡列表 → 上下键选择难度 → Start 下一步 → 六人出战页。B 逐级返回。

存在未结束的探索时，区域图仅保留该区域名称，其他区域显示「未解锁」，底部仍有「探索收集」「作战机略」。关卡列表同样只开放正在处理的难度；Start 出现「当前正在处理：〔关卡〕 是否继续？」弹窗，黄色确认按钮获得焦点时 A 返回原探索。见 `resumed-entry-failure.webp`、`resumed-locked-entry-levels.webp`、`resumed-continue-prompt.webp`。

区域图中的绿色 A 提示位于当前区域名称下方；名称紧下方的绿色圆点是通关进度，不是焦点。实拍中，资质考核按右到旧都列车，再按上到施工废墟。

## 关卡列表

右侧显示完整名称，例如「旧都列车·内部」或「施工废墟·内部」。黄色矩形表示当前选择。底部「关键敌情」与「下一步」可以区分区域图和关卡列表。列表移动只改变选择，Start 进入编队；不能以最初选中的最高难度替代配置指定的内部。

## 六人出战页

上排显示领队和队员，下排是候补。下排三个 EMPTY 不能证明全队为空。此页底部左侧为「战斗设置」，与迷失之地三人页的「预备编队」不同。Start 为出战；本次未改动已有队员。

## 识别快照

| 子态 | 文字与位置（1080p） | 截图 |
|---|---|---|
| 区域图 | 资质考核 (219,682)、施工废墟 (691,366)、旧都列车 (614,781) | `screens/零号空洞-入口/withered-type-right.webp` |
| 关卡列表 | 旧都列车·外围／前线／内部／腹地／核心，右侧五行；关键敌情 (1409,1011) | `screens/零号空洞-入口/withered-old-train-levels.webp` |
| 施工废墟 | 前线／内部／腹地／核心，内部为第二行 | `screens/零号空洞-入口/withered-construction-selected.webp` |
| 编队 | 领队、队员、下排 EMPTY、战斗设置、出战 | `screens/通用-枯萎出战/withered-current-team.webp` |

## 电视地图、事件与鸣徽

电视地图使用方向键走相邻格，移动后邦布头像出现在新格。触发事件时地图会被放大电视或选项面板覆盖；必须等事件结束后再观察当前位置。实拍移动见 `screens/零号空洞-事件/withered-map-stable.webp` 与 `withered-after-left-stable.webp`。

事件右侧选项以黄绿色填充表示焦点，焦点项是黑字，其他选项是白字。上下切换、A 确认。普通对话的继续 A 提示位于右侧 (1832,568)；选项左侧的 A 不是继续对话。截图 `withered-current-state.webp`、`withered-initial-map.webp` 分别记录选项和普通对话。

鸣徽页的名称位于 y=470～535，卡片左右选择、A 确认。研究型鸣徽只有中间一张，标题为「请领取怀斯塔学会的研究型鸣徽」；普通选择有三个卡槽。「不可触碰之物」是不可选的占位卡，其余卡牌依然按名称区分。实拍覆盖三张可选、两张可选和一张可选，见 `withered-tv-first.webp`、`withered-reduced-cards.webp`、`withered-reduced-selected.webp`。

X 翻转当前焦点卡。背面名称移到 y=315～365，原名称位置显示效果描述；战斗结束的残留 X 也可能触发。识别到背面名称且它位于唯一黄色焦点框内时，按 X 翻回，再读取全部正面名称选择。实拍见 `fresh-run-card-failure.webp`、`flipped-card-before-fix.webp`、`flipped-card-restored-by-fix.webp`。

侵蚀消息、代理人入队消息和零号业绩奖励使用居中的黄色「确认」按钮，下方有 A「选择」。按钮高度随内容变化，确认区域为 (800,590)～(1120,770)，提示区域为 (800,690)～(1120,840)。见 `withered-researcher-choice.webp`、`withered-support-joined.webp`、`withered-second-card-failure.webp`。零号业绩奖励同样带有「选择」提示，不能据此判定是鸣徽三选一。

呼叫增援依次选择接应、队伍位置、确认入队消息。位置选项的顺序可能是 2 号位、1 号位、返回，不能按视觉顺序推定槽号。入队后底部出现对应角色头像。见 `withered-support-position.webp` 与 `withered-support-stable.webp`。

清除侵蚀页显示五个卡槽，已生效的侵蚀有名称和可用「清除」按钮。左右切换、A 清除；黄色边框围绕卡片，按钮也变黄。见 `withered-mouse-retry-fixed.webp`。

及时补给页的焦点只标在底部按钮，三项分别为「回复生命值」「获得齿轮硬币」「降低压力值」，不能使用鸣徽卡片边框识别。见 `withered-after-large-tv.webp`。旧都失物查看页底部 B 返回，A 用于播放音频，不能用 A 代替关闭。见 `withered-gate-confirm.webp`。

双重危机的大电视在战斗后拆成四个小格，当前位置只占原区域的一部分，见 `withered-full-run.webp`。普通战斗实拍见 `screens/零号空洞-战斗/withered-post-lost-item.webp`；本次战斗结束后直接回到探索并出现鸣徽页 `withered-battle-reward.webp`。

商店外层上下选择鸣徽交易或鸣徽催化，A 进入、B 返回。选项的白色图标会截断黄色底色，文字底色仍能表示选中。商品列表上下移动，当前商品左移并显示 A；黄色价格表示可支付，红色表示不足。A 直接购买，战利品页 A 确定后回到商品列表。B 先回外层，再按 B 离开商店。实拍见 `screens/零号空洞-商店/withered-current-shop.webp`、`withered-shop-items.webp`、`withered-shop-priority.webp`、`withered-shop-purchase.webp`。

购买后的卡槽可能继续显示原名称和灰色价格，卡面变暗并出现单据图案，不一定有「售罄」文字。`third-shop-failure.webp` 中碳卡已买入，余额降至 199，其他两项价格变红；灰色价格的已购卡应排除。

事件也可直接发放一张或多张鸣徽，使用同一「获得战利品」标题与底部 A「确定」按钮；此页没有选卡动作。两张战利品实拍见 `screens/零号空洞-事件/withered-rift-run-live.webp`。事件选项的同一行文字可能被 OCR 拆为多段，选中变为黑字后又合为一段，见 `withered-rift-selected.webp`。

第一层首领结束后显示「挑战结果」、S 评价、用时及奖励，底部有 X「暂离」和 A「确定」。确认后可能先出现诡术鸣徽重构、三选一奖励、集齐同类后的进阶鸣徽，再恢复下一层电视地图。本次从 1/3 进入 2/3，见 `screens/零号空洞-战斗/withered-boss-result.webp`，以及事件目录的 `withered-after-boss-confirm.webp`、`withered-next-floor.webp`、`withered-floor-after-rewards.webp`、`withered-floor-2-ready.webp`。重构和进阶鸣徽卡的确认按钮约在 y=790，与普通战利品的 y=845 不同。

施工废墟的结果页中，三层进度条遮住「挑战结果」标题下半部，OCR 无法可靠读取标题；「总计用时」「完成关卡」与底部「暂离」「确定」仍完整可见，可共同识别结果页。见战斗目录 `quick-result-routing.webp`，本次第一层用时 56 秒、S 评价。

最终首领后出现「MISSION COMPLETE」和三层勾选，奖励位于右侧，底部 B「完成」退出到区域选择页；旧版「街区」文字此时不存在。X 查看侵蚀、Y 打开探索总结，总结页 B 返回结算。见 `withered-final-result.webp`、`withered-end-live.webp`、`withered-final-exit-state.webp`。结算缺少旧坐标上的丁尼图标不能证明周期奖励已满。

在「门扉禁闭·善战」相邻格按方向键，只会出现「开门」选项；A 开门后头像仍在原格，需要再次向门移动才进入。见 `withered-floor2-stuck.webp` 与 `withered-door-opened.webp`。开门条件为上一场守门人战斗取得 S 评价。

第三层的「残破的障碍物」需连续撞击多次才破开；此前头像保持原位，不能当成已进入目标格。实拍 `withered-floor3-diagnose.webp` 与 `withered-wall-hit3.webp` 记录破墙前后。

墙后不一定是空格：第二层实拍破墙后露出「鸣徽催化剂」，头像仍在原格，见 `wall-failure-detail.webp`。这时应重新规划进入已显露的格子，不能继续等待头像自动移入。

鸣徽催化结果会并排显示同名的原卡和强化卡，下方只有 A「确定」，无需二选一。见 `withered-third-latest.webp`。

防卫军后勤站「公平交易」后出现「丢弃冗余」预览，可横向浏览多张鸣徽。卡片焦点只用于查看与 X 翻面，卡片上的 A 不执行单卡丢弃；下移到底部黄色「丢弃」按钮后 A 统一结算，随后出现多张「获得战利品」。这是按游戏规则处理整批的交易，不能在此页按优先级保留单张卡。见事件目录 `fresh-withered-drop.webp`、`fresh-withered-drop-confirm-focus.webp`、`fresh-withered-drop-after-confirm.webp`。其他事件是否使用同标题尚未观察。

催化选择标题为「请选择要催化的鸣徽」，可选数量受未强化鸣徽数量限制，实拍 `catalyst-choice-failure.webp` 只有一张居中卡牌，A「选择」。先从完整彩色卡框确认数量，再核对每张卡的名称，不能固定要求三张。

首领「挑战结果」页的 X 是暂离；战斗残留 X 可能打开「是否确认暂停空洞探索，返回街区？」弹窗。该弹窗 B 可取消并回到原结果页，A 会确认暂离。实拍见战斗目录的 `boss-pause-prompt.webp`、`boss-pause-cancelled.webp`。后台识别到完整提示和取消按钮后先停止战斗输入，再用 B 取消，随后仍需识别「挑战结果」与「确定」才能继续。

暂离弹窗也实测在首次结果确认之后出现，因此等待换层期间仍需辨认并取消，回到结果页后重新确认；不能将其视为加载等待。新增实拍 `fresh-withered-floor-wait0110.webp`、`fresh-withered-result-before-confirm.webp` 留档了该失败和取消后的状态。

## 邦布插件与主动退出

本机当前设置下，X 短按打开邦布插件列表，左右切换已有插件，空槽会被跳过；只有一个插件时按右仍选中原插件。当前选中名称显示在中部灰条，A「使用」，B 返回。实拍交叉爆破使用后数量归零、入口消失，十字范围内事件格被清除。不同快捷使用设置下长按与短按可能交换，页面说明有明确提示；不以列表消失前的按键本身认定使用成功。

Start 打开「战况」菜单，底部 X「暂离」、Y「放弃」、A「选择」、B「返回」。Y 弹出「是否确认放弃空洞探索，返回街区？」；确认按钮默认黄色焦点，A 确认，B 取消。暂离与放弃是两种操作，不能混用。

实拍位于测试仓事件目录：`quick-plugin-tap.webp`、`quick-plugin-right.webp`、`quick-plugin-used.webp`、`quick-menu-start.webp`、`quick-abandon-confirm.webp`。

放弃后显示 `MISSION FAILED` 结算，底部 B「完成」返回入口，见 `quick-abandon-result.webp` 与 `quick-exit-completed.webp`。这不代表完成了三层探索。

插件格会弹出「获得邦布插件」，中间显示插件图标及名称，底部为「确定」和 A「选择」。这是一条取得物品的消息，不是鸣徽选择，见 `quick-plugin-acquisition.webp`。

投机客拒绝借款后仍可能提供援助，后续页只有「恢复身体／回复10%生命值」和「清除压力／压力值-20」，没有离开按钮；见 `quick-speculator-state.webp`。上下选择、A 确认。

盲盒区域也可能是 3×3 小图，包含安全区、休息区和「不宜久留」出口；从中央直接向下即可进入出口。离开后回到剩余三格的主图，见 `fresh-blindbox-entry.webp` 与 `fresh-blindbox-return.webp`。不能将盲盒固定为多列环形布局。

盲盒也可能直接在主图结算，不出现独立区域和「不宜久留」出口。实拍 `second-blindbox-before.webp` 与 `second-blindbox-after.webp` 中，盲盒右侧硬币、财富门和危机仍保持相对位置，头像进入原盲盒格，整行缩短并居中。

另有五格十字形盲盒，头像在上，出口在下，中间一排三格；按钮可能识别为未知，休息区可能误识成双重危机。速刷只走中央格到出口，见 `cross-blindbox.webp`。若主图原先仅剩盲盒和商人，返回后只剩头像、商人两格，见 `cross-return-current.webp`。
