# 星願小王子 (Starwish Little Prince) — English Guide to the Game Suite

A guide to the 星願小王子 learning-software family, compiled from the published
user manuals and the publisher's own product pages (Starwish Fair / Starwish
Little Prince Ltd.). Where the sources do not say something, this guide says
**"not stated in the manual"** rather than guessing.

---

## 0. How this guide was made, and how to read the Chinese names

* The manual index page (`學習軟件使用手冊`) is JavaScript-rendered and holds no
  text of its own: it is a list of links to per-product PDF manuals on
  `little-prince.com.hk`.
* Those manual PDFs are **scanned page images with no text layer**. They were read
  by a mix of OCR and visual reading of the page images. Titles and labels below
  are transcribed as printed; a few characters in the smallest headings are
  uncertain on the scan and are flagged where that matters.
* Everything labelled as coming from a "product page" is the publisher's own shop
  description for that title on `starwish-fair.com`, not the paper manual.
* Chinese is kept only for names and on-screen labels; each is explained in
  English.
* The manuals themselves are Traditional Chinese and say: 所有內容以實際遊戲為準
  ("all content is subject to the actual game"), so screen wording can differ from
  the booklet.

**Code mapping (this project's codes vs. the publisher's naming)**

| Code | Publisher's name | Also sold as | Manual read |
|---|---|---|---|
| LP1 | 《星願小王子》 | 星願小王子 I – 全新雲端版 | `星願小王子使用手冊.pdf` (16 pp.) |
| LP2 | 《星願外傳》 | 星願小王子 II – 星星失落之謎 | `星願外傳使用手冊.pdf` (9 pp.) |
| LP3 | 《星願歷奇》 | 星願小王子 III – 農場大作戰 | `星願歷奇使用手冊.pdf` (9 pp.) |
| LPO | 《星願小王子》Online 系列 (星之國 Online) | 星願小王子 – 星之國 Online 全集, or per episode 第 1–9 集 | `Online使用手冊.pdf` (21 pp.) |

Two more titles exist on the same site and are listed on the same manual index
page but are outside the set this guide was asked to cover:

* **LP4 星願思語 (星願小王子 IV – 星願思語．星空聯盟)** — manual PDF is published
  (`星願思語使用手冊.pdf`, 30 pp.), and the site splits it into five themed
  sub-titles: 水后星, 木將星, 土帥星, 火王星, 金爵星.
* **LP1(R) 星夜重圓** — listed in the site navigation, but the manual index page
  shows it as plain text with **no manual link** (nothing to read).

---

## 1. What the whole suite is for

Taken from the shared "product philosophy" pages and the manual prefaces:

* **Aim:** 寓學習於娛樂 — "learning through play". The suite is a set of Chinese
  (and later English/maths) **interactive learning games** built to train
  reading, writing and perceptual skills.
* **Origin (from 《星願小王子》的由來):** developed jointly by 三水同鄉會劉本章學校
  (a Hong Kong school that supports mainstream schools on **讀寫障礙 / dyslexia**)
  and 新怡互動創作有限公司, starting in 2005 under an Education Bureau scheme for
  teaching-software development. The software was created to give children easy
  reading-recognition and learning practice.
* **Who it is for:** primary-school children doing Chinese literacy work, and
  especially children who need extra reading/writing (dyslexic-type) support.
  A precise age or grade band for LP1/LP2/LP3/LPO is **not stated in the manuals**
  (only LP4's shop page states a band: 幼稚園至高小, kindergarten to junior primary).
* **Three teaching strands** run through every title:
  1. **多感官教學** multi-sensory teaching — visual tracking, visual memory,
     eye–hand–brain coordination, image-based learning.
  2. **識字教學** character teaching — 形 (shape), 音 (sound), 義 (meaning);
     radicals/radical components (部首/部件), stroke order (筆順), character
     structure (字形結構), homophones (同音字).
  3. **思維訓練** thinking training — spot-the-difference, story sequencing,
     reasoning, categorisation, inference, creativity.
* **Shared devices across titles:** a **成績表** (report card) per child that
  records each game and each level (newest / first / best score) plus collected
  items and completion; **語音支援** voice support with Cantonese, Mandarin and
  (in later titles) English readings, with pinyin shown for Mandarin; and
  **levelled games** (each game has multiple 關卡, levels, that open one after
  another as the child passes).

---

## 2. Installing, activating and logging in (all titles)

Two delivery routes are sold: **家庭/家用版** (home edition, a download with the
company's own browser) and **機構/學校授權版** (school/institution licence).

### 2.1 Home edition — install (PC)

Source: `星願小王子_星願外傳_星願歷奇_家用版軟件下載及安裝步驟--PC.pdf` (demonstrated
on Windows 10):

1. Download the home-edition software from
   `http://www.little-prince.com.hk/littleprince/Download/LittlePrinceBrowserHome.zip`.
2. Right-click the downloaded `.zip` and unpack it with 7-Zip (*Extract Here*);
   7-Zip itself comes from `https://7-zip.org/download.html` if not installed.
3. Move the unpacked `LittlePrinceBrowserHome` folder into
   `Program Files (x86)`; answer 繼續 ("Continue") if it asks for administrator
   rights.
4. Open the folder and right-click `LittlePrinceBrowserHome.exe` → 釘選到工作列
   ("Pin to taskbar"). Clicking the **little-prince icon** on the taskbar opens
   the game site.

### 2.2 Home edition — install (Mac)

Source: `..._家用版軟件下載及安裝步驟-MAC.pdf` and
`星願小王子Online_家用版軟件下載及安裝步驟-MAC.pdf` (demonstrated on macOS High
Sierra 10.13.6):

1. Download `LittlePrinceBrowserHome-Mac.zip` (for LP1/LP2/LP3) or
   `LittlePrinceBrowserOnline-Mac.zip` (for the Online series).
2. Drag the app from 下載項目 ("Downloads") into 應用程式 ("Applications").
3. Drag it to the Dock to make a shortcut, then click the prince icon; press
   打開 ("Open") when macOS asks.

### 2.3 Account registration and activation

**LP1/LP2/LP3 home (cloud) version** — the LP1 manual devotes a page to this
(page marked 此頁學校版不適用, "not applicable to the school version"). Three steps:

1. **戶口註冊** — go to `www.little-prince.com.hk/LP/personal`, choose
   **綁定產品至雲端版** ("bind product to cloud edition"), enter your personal
   details and the game serial number, press **提交** ("Submit").
2. **戶口啟動** — a confirmation e-mail (確認電郵) arrives; click the link to
   activate the account. If it is missing, check the junk/spam folder, or e-mail
   `enquiry@little-prince.com.hk`.
3. **開始遊戲** — go back to the same URL, choose **進入遊戲** ("Enter game"), and
   after the animation enter your username and password and press **登入**
   ("Login").

The PC install guide adds plainly: **用戶名稱 = 登記了的電郵地址** — your user name
is the e-mail address you registered with — and that for errors, or if no e-mail
arrives, you should contact the publisher (`T: 3583 2665`) **instead of**
re-registering.

**LPO (Online)** — from the Online manual's 戶口註冊及產品啟動 page (also marked
not needed by school-version users):

1. Open `www.little-prince.com.hk/prince_online/`, or install the home-edition
   browser (Mac 版 / PC 版).
2. **免費註冊** — if you have no 星之國 account, register one
   (button: 註冊戶口) and follow the instructions to activate it.
3. **產品啟動** — press 產品啟動 and type the serial number printed on the
   serial card inside the box to activate the product.
4. **開始** — return to 主頁 ("Home") and click **星願帳戶** (or **CloudKey帳戶**);
   load it, log in one more time, and the game starts. The manual also offers a
   **免安裝網上版** (no-install web version).
5. Buying later episodes: log in at 帳戶管理 ("Account management") and activate
   the new episode (stated in the Mac install guide for Online).

### 2.4 System requirements

From the publisher's own product pages for LP1, LP2, LP3 and LPO — all identical:

* 處理器 CPU: 雙核心 1.4GHz 或以上 (dual-core 1.4 GHz or above)
* 記憶體 RAM: 1GB 或以上
* 瀏覽器 Browser: Internet Explorer or above, Firefox or Chrome, **or** the
  company's own 星願小王子瀏覽器 (downloadable from the 軟件下載及安裝指引 page)
* 必須連接互聯網使用 — an internet connection is required
* Platform: 桌面或手提電腦 (desktop or laptop): Windows or macOS
* 不適用於 Android 或 iOS 平板電腦或智能手機 — not for Android/iOS tablets or phones

Related stated requirement worth noting: the shop page for **LP4** lists 記憶體
16GB 或以上 (16 GB RAM) and browser login at `www.starwish-fair.com`, and LP4 is the
only title the site says also has an iOS app and 跨平台 (cross-platform) use.

---

## 3. LP1 — 《星願小王子》 ("Little Prince")

### 3.1 Which game it is
The first title of the 讀寫系列 (reading/writing series), sold as *星願小王子 I –
全新雲端版* (download edition). The manual cover carries the tagline
輕鬆讀寫樂悠悠 and four selling points: **增強讀寫能力** (strengthen
reading/writing), **改善記憶力及專注力** (improve memory and attention),
**17款學習遊戲** (17 learning games), **專業粵語及普通話讀音** (professional
Cantonese and Mandarin readings).

### 3.2 Who it is for
Children practising Chinese reading and writing — the whole design is aimed at
**認字 / 讀寫** (character recognition, reading and writing), with visual-tracking
and visual-memory drills meant to help children who mix up similar-looking
characters (減少因字形相似而誤寫別字). No specific age band is **stated in the
manual**.

### 3.3 The story
Long ago in 星之國 (the Kingdom of Stars) a happy prince prayed to the stars every
night. One night the stars began to fall from the sky; the land grew dark. To find
the lost star fragments the prince leaves the palace and searches the world for
**星星元素 (star elements)** so that the land can shine again.

### 3.4 How it plays, and how you progress
* The star elements are scattered over **17 places in the world**, grouped into
  **3 regions**, each with its own learning function:
  * **海洋區域** Ocean region — 多感官學習 multi-sensory learning
  * **陸地區域** Land region — 字詞學習 word learning
  * **移動城堡區域** Moving-castle region — 思維學習 / 思維訓練 thinking training
* You sail to marked places on the map and play the game there. Each game has
  several **關卡** (levels). Clearing a level **automatically opens the next**;
  the higher the level, the **more and rarer** the elements it gives.
* **隱藏元素 (hidden elements)** appear **randomly at high-difficulty levels** —
  the manual presents these as the discovery part of the game.
* When you have collected enough elements you use the in-game **製作手冊**
  (crafting manual) to make stars for the sky. **Collect all 17 main stars and the
  world is restored to its former brightness.** (The shop description words the
  same goal as 集齊十七顆主要星星.)

### 3.5 Rewards, currency and the report card
* The soft currency is **星星元素 (star elements)**, in a basic kind and a rarer
  hidden kind; the meta-reward is the **17 stars (星星)**.
* **部首咭 (radical cards):** bought with your scores, then printable — the child
  can use them to build the characters they know or like, or swap them with
  friends.
* **成績表 (report card):** shows each game's per-level average, first and best
  score, plus 已獲取的基本元素 (basic elements obtained), 隱藏元素 (hidden
  elements), 部首咭, the number of stars owned and 遊戲完成程度 (completion).
  Parents are told they can use it to spot strengths and weaknesses.
* **語音設定 (voice settings):** in the 遊戲設定 (game settings) panel at the
  top-right of the map screen the child can set 語言 to **粵語** (Cantonese) or
  **普通話** (Mandarin) and set 重播模式 (replay mode) to 開啟/關閉 (on/off).
  Correct answers are read out.

### 3.6 The 17 learning games

**海洋區域 — 多感官學習遊戲 (Ocean region — multi-sensory learning games), 7 games**

| Game (Chinese) | Type | How you play | Levels (關卡) |
|---|---|---|---|
| 漩渦影無蹤 | visual tracking | Objects drift past in the whirlpool current from different directions; watch closely, then choose the right answer. | 海洋生物 · 字母/數字 · 中文單字 · 中文詞語 · 短句 |
| 閃光怪魚 | visual concentration | In a pitch-dark sea cave a glowing fish flashes objects into view; count the objects and pick the answer. | 粗幼線條 · 圓圈 · 基本圖形 · 海洋生物 · 移動的海洋生物 |
| 鯨魚泡泡 | visual exploration | The whale blows bubbles carrying objects; follow the prince's prompts and hit the bubbles in the right order inside the time limit. | 數字 · 倒數 · 單數 · 雙數 · 英文字母/海洋生物 · 部首 |
| 海底大觀園 | visual memory | Objects appear among the coral then are washed away; remember where each was and put them back. | 字母、數字 · 中文單字 · 中文詞語 · 不同顏色的魚 · 海洋生物 |
| 消失的文字 | visual memory | Words vanish from the text on the sail; fire the harpoon at the fish carrying the right answers, in order. | 30字文章 · 50字文章 · 70字文章 |
| 八爪魚吐墨記 | visual memory (order) | Watch the order in which the octopus eats the objects around it; after the ink cloud, put them in that order. | 字母、數字 · 中文單字 · 中文詞語 · 海洋生物 |
| 色色相關小魚仙 | visual memory (colour) | Remember the order in which colours appear on the clam; refill them in the same order with the palette at the bottom right. | 海洋生物 · 動物 · 景物 |

Aims as printed: attention, visual tracking, visual memory (colour, order,
position), visual exploration, and recognising the features of similar-looking
characters so the child makes fewer 別字 (wrong-character) mistakes.

**移動城堡區域 — 思維學習遊戲 (Moving-castle region — thinking games), 3 games**

| Game | Type | How you play | Levels |
|---|---|---|---|
| 移動故事城堡 | story sequencing | Empty frames hang in the castle; drag pictures into them to arrange a meaningful sequence. | 生活事件 · 詩歌 · 故事 |
| 旗異密室 | spot-the-difference | Two different flags fill the chamber; within the time limit, click every difference between the two pictures. | 圖畫 · 生活事件 · 字母、數字 · 文章 |
| 文字迷宮 | word maze | Use the arrow keys to walk the prince out of the correct exit of the maze, following the meaning and structure of sentences. | 5個詞語 · 6個詞語 · 8個詞語 |

Aims as printed: handling information, story organisation, visual attention,
analysis and discrimination, reasoning, plus reading/writing and language skill.

**陸地區域 — 多感官學習遊戲 (Land region — multi-sensory learning games), 7 games**

| Game | Type | How you play | Levels |
|---|---|---|---|
| 部首馬戲團 | radical analysis | In the circus tent, throw darts at the right 部首/部件 on the target to build the correct character. | 部首(左右) ×2 · 部件(左右) ×2 |
| 字在雲中尋 | character structure | Clouds cover a character on the snowy mountain; brush the clouds aside with the mouse, guess the character and click the right answer. | 左右 · 上下 · 半包圍 · 全包圍 · 品字形 · 混合 |
| 詞語激流 | word learning | Lily pads drift in the rapids; use the arrow keys to make the prince jump onto the pad holding the correct word until he reaches the bubble. | 速度慢 · 速度中 · 速度中快 · 速度快 |
| 古城揭秘 | guess-the-character from pictures | Egyptian patterns on the pyramid door hide a character riddle; match identical patterns with the mouse to reveal clues and guess the character. | 圖配圖 · 圖配詞語 · 詞語配詞語 · 同音字配同音字 · 部首配部件 |
| 字磚噴水池 | component construction | Click the right components into their correct places on the 字形尺 (character ruler); when the character is complete a whole brick appears beside the pool. | 左右 · 上下 · 半包圍 · 全包圍、三合形 · 品字形 · 混合 |
| 玻璃字城 | stroke order | Characters appear on the frozen window of the train; following the ticket inspector, trace the strokes with the mouse in the correct order. | 二至四劃 · 五至七劃 · 八至十劃 |
| 明鏡照天詞 | fill-in-the-word | The water sprite lays out water mirrors on the lake; follow the prompts and use the mouse to find the correct word in the mirrors. | 9塊 · 16塊 · 25塊 |

Aims as printed: eye–brain–hand coordination, awareness of 形/音/義, character
structure and radicals/components, stroke-order principles and stroke knowledge,
visual exploration and observation, reasoning.

*(Game names, types, level lists and aims above are transcribed from the scanned
manual pages; individual characters in the smallest headings are the ones most
affected by scan quality.)*

---

## 4. LP2 — 《星願外傳》 ("Starwish Legend")

### 4.1 Which game it is
Second title of the series, sold as *星願小王子 II – 星星失落之謎* (the answer to
the mystery of the falling stars). The manual cover reads 星願外傳 / 全新雲端版 /
**星星失落之謎**, describes it as 互動語文學習遊戲 (interactive language learning
games) and lists **提升語文能力** (raise language ability), **改善記憶力及專注力**
and **20款學習遊戲** (20 learning games). *(Note: this project's context file
labels LP2 with the subtitle 「星座消失之謎」; the manual cover and shop page both
print 星星失落之謎.)*

### 4.2 Who it is for, and how it differs from LP1
Same audience as LP1, but the manual is explicit about the progression of
content: it extends the depth and breadth of the three strands into parts of
Chinese characters that LP1 did not cover (規律、形體、特點、讀音及結構 — patterns,
forms, features, pronunciation and structure). **The distinctive focus is sound:**
where LP1 stresses 字形 and 字義 (form and meaning), LP2 stresses the pairing of
**字音** — 形聲字 (phono-semantic characters made of a 形符 meaning element plus a
聲符 sound element), 一音多字 (one sound, many characters), and the fact that
characters built from the same component can be homophones or near-homophones.
The stated purpose is to reduce **同音替代** errors (writing a same-sounding but
wrong character) in children with weaker reading.

### 4.3 The story
In LP1 the stars of 星之國 fell and were rebuilt. Now the prince learns from his
father that the stars' energy comes from **幻想空間 (Fantasy Space)**, and a star
virus has invaded it so the stars lose their power. The prince enters Fantasy
Space, which has **four regions — 糖果世界 (Candy World), 不思議世界 (Wonder
World), 迷之花園 (Enchanted Garden) and 幻影之砂 (Phantom Sands)**. His sister
**星願小公主** follows him with a treasured **魔法陣** (magic circle) device that
opens the doors of the **能量塔** (energy towers). The source of all viruses,
**病毒大王 (the Virus King)**, hides in a two-dimensional space and only appears
once every virus envoy has been destroyed.

### 4.4 How it works and how you progress
* **Success threshold:** to collect star energy you must finish a game in a region
  with a success rate **above the preset target (成功指標)**. Only then does the
  energy appear on that region's map and the **next level open**.
* **Energies:** base energies are the five elements — **金木水火土 (metal, wood,
  water, fire, earth)**. **神祕能量 (mystery energies)** — 白光鑽, 黑光鑽, 幻彩鑽,
  月晶寶石, 藍晶寶石 — appear **only randomly at high difficulty levels**.
* **Crafting items:** with enough energy, visit a **守護使者 (guardian envoy)** who
  is the region's expert in forging energy into 道具 (items). You then arrange the
  energies in the **魔法陣** as the in-game **星之鏡** (mirror) instructs, producing
  weapons and gear used against virus envoys.
* **Bosses:** fighting a virus envoy is done after equipping the right items,
  using the princess's magic circle to reveal a 智慧之實物 (wisdom object) that
  opens the energy-tower door.
  * Virus envoys: **N6B3 蛀牙蟲** — 病毒能量指數 20,000 (a floating high-toxin type
    that feeds on sweets); **米斯變形蟲** — 10,000 (an invasive type with high
    defence and electrical discharge); **N6B5 四葉食人草** — 17,000 (a poisonous
    fast-growing vine); **病毒大王** — 病毒能量指數 ??????? (unknown).
  * Guardian envoys: **木之使者 格蘭特**, **火之使者 伊弗列特**, **水之使者 滴滴**,
    **金之使者 艾美莉**, **土之使者 杜卡**.
  * In 幻影之砂 a **試煉影子赤烈** has built a 試煉武場 (trial arena) and waits
    for the prince's challenge; beating him wins a legendary **魔法指環**.
* **成績表:** records each game and level (newest / first / best score) plus the
  star energy obtained, mystery energy, number of items owned and completion.

### 4.5 The 20 learning games

**不思世界 — 多感官訓練區 (Wonder World — multi-sensory training), 6 games**

| Game | Type | How you play | Levels |
|---|---|---|---|
| 迷幻之森 | visual memory | The prince must lead an old man out of the enchanted forest; remember where objects appear, and when the screen darkens drag the prince to the right exit. | 5 levels, shallow to deep; the light ring shrinks, obstacles increase and the screen darkens faster |
| 時光隧道 | auditory memory | The prince floats in a time tunnel — keep tapping the left mouse button to stay airborne and touch the correct answer that appears in the picture and sound prompts. | 5字句子-單字 · 5字句子-2個單字 · 5字句子-2個詞語 · 6字句子-2個單字 · 7字句子-2個單字 · 7字句子-2個詞語 · 7字句子-3個詞語 |
| 湖神倒影 | visual tracking | Objects float past the lake god upside down; click the correct answer. | 食物/污染物 · 字母/數字 · 中文單字 · 中文詞語 · 短句 |
| 石魔浮橋 | auditory memory (order) | A stone man chases the prince; click the bridge components and drag them into place to rebuild the complete sentence. | 重組三塊 · 四塊 · 五塊 · 六塊 · 七塊 |
| 神秘洞穴 | visual tracking | A giant worm coils the prince up; match the symbols shown on the cave wall by clicking the same symbols on the worm. | 字母 · 數字 · 中文單字 · 中文詞語 · 圖形及顏色 |
| 奇妙泡泡 | visual exploration | Strange bubbles blow out objects; find the right item from the on-screen prompt and click it. | 圖像 · 數字 · 字母 · 中文單字 · 中文詞語 · 成語 |

**糖果世界 — 字詞學習區 (Candy World — word learning), 8 games**

| Game | Type | How you play | Levels |
|---|---|---|---|
| 字詞瀑布 | word matching | Use the arrow keys to make the prince jump onto the right marshmallow in the chocolate waterfall to form words. | 速度慢 · 速度中 · 速度中快 · 速度快 |
| 部件雪糕屋 | radical/component analysis | Make an ice-cream sundae: click the correct 部件/部首 scoop and shoot it to the correct position to form the character. | 左右(左) · 左右(右) · 上下(上) · 上下(下) · 半包圍(上) · 半包圍(下) |
| 字形糖果店 | character structure | Steer a sweet with the mouse to touch sweets of the same 字形結構; the sweet keeps growing and changing structure, and touching a star makes it shrink. | 2種字形尺 · 3種 · 4種 · 5種 · 6種 · 7種字形尺 |
| 部首糕庫 | component construction | In the pastry store-room, use the arrow keys to push characters with the same 部首 into the same row, and characters with the same 部件 into the same column of the grid. | 2x2格 · 2x3格 · 3x3格 · 3x4格 |
| 象形餅屋 | pictographs | Biscuits pave the floor of the biscuit house; use the mouse to move the prince quickly to the modern character that evolved from the pictograph. | 6 levels, shallow to deep — pictograph difficulty, other characters' speed and precision increase |
| 同音啫喱糖 | homophones | Jelly sweets sit on the board; click to pair the different homophones. | 4個同音字(20塊) · 2個同音字(20塊) · 4個(30塊) · 2個(30塊) · 4個(40塊) · 2個(40塊) |
| 成語果撻 | idiom jigsaw | First assemble the picture in the frame in front of the machine, then drag the falling strawberries into the fruit tart in the order of the idiom to complete it. | 4張砌圖 ×3 · 6張砌圖 ×2 |
| 筆順蛋糕 | stroke order | Use the mouse to draw the cream on the cake in the correct stroke order. | 二至四劃 · 五至七劃 · 八至十劃 · 十一至十三劃 |

**迷之花園 — 思維訓練區 (Enchanted Garden — thinking training), 3 games**

| Game | Type | How you play | Levels |
|---|---|---|---|
| 不可思議老頭 / 不可詩義老頭 (scan reading) | poetry game | Read two poems, use the mouse to choose the correct poem for the meaning, then drag the lines back into the right order. | 2選1(排2/3/4句) · 3選1(排2/3/4句) |
| 構形稻草人 | component construction | A board stands in the rice field; drag the character components from the leaves onto the board to build the correct character. | 上下、左右 · 半包圍 · 上中下、左中右 · 左右下、左上下 · 混合 |
| 石像花園 | reasoning | One stone statue in the garden has lost its crown; use the clues shown on the other statues' crowns to work out and click the right crown. | 6條柱: 圓形/數字/英文字母 · 5條柱: 常用序列/分類 · 4條柱: 部首/部件 · 4條柱: 詞類 |

**幻影之砂 — 英數遊戲區 (Phantom Sands — English & maths games), 3 games**

| Game | Type | How you play | Levels |
|---|---|---|---|
| 浮沙古城 | maths equations | In the sphinx, use the mouse to pick up and place golden bricks on the chest to complete the equation — while dodging the mummy's attacks. | 兩個整數 · 兩個小數 · 兩個分數 · 三個整數 · 三個小數 · 三個分數 |
| 獅身祕寶 | rebuild English sentences | Rocks keep falling in the underground city; use the arrow keys to control the prince and the bomb to complete the correct equation/sentence, rearranging the golden bricks to rebuild the sentence. | 難度低 · 難度中 · 難度中高 · 難度高 |
| 食人魚潭 | English vocabulary | Piranhas chase the prince; move the mouse to change his direction and place the English letters in the correct positions following the prompts. | 字長度短 · 字長度中 · 字長度長 · 字長度最長 |

Aims as printed across the region: attention, visual tracking and memory,
auditory memory (order and sequence), discrimination of similar-looking
characters, character structure and components, homophone awareness,
reasoning (e.g. 石像花園), fast arithmetic and reverse thinking, English
sentence structure and vocabulary, English typing and Chinese input.

---

## 5. LP3 — 《星願歷奇》 ("Prince Adventure")

### 5.1 Which game it is
Third title, sold as *星願小王子 III – 農場大作戰* ("Farm Battle"). The manual
cover reads 星願歷奇 / 全新雲端版 / **農場大作戰**, 互動語文學習遊戲, with
**提升語文能力**, **24個全新中英數遊戲** (24 brand-new Chinese, English and maths
games) and **專業粵語、普通話及英語發音** (professional Cantonese, Mandarin **and
English** pronunciation). LP2's manual also states that its games carry Chinese and
English readings, with the Chinese voice selectable as Cantonese or Mandarin; LP1's
cover advertises Cantonese and Mandarin readings.

### 5.2 Who it is for
Same target as LP1/LP2 (children working on Chinese literacy and cognitive
skills), with the same three strands again extended. Like LP2 it keeps the
**字音 (sound) focus** — phono-semantic characters, 一音多字, homophones and
near-homophones — but adds **English and mathematics learning games** in its own
regions. No age band is **stated in the manual**.

### 5.3 The story
Inside 星之國 there is a village, **星之村**, owned by a farmer called **凡達
(Fanda)**. A **狼人 (werewolf)** has been raiding the farm and ruining the crops.
Hearing that the prince defeated 病毒大魔王, Fanda asks for help. The werewolf
stole the **星之珠 (star pearls)** and is being driven mad by the **慾望之石**
(stone of desire). To deal with the werewolf you must collect the star pearls
scattered across the farm and make the **星之咭 (star cards)** that can beat him.
Other characters: Fanda's son (who has been missing a long time), the werewolf's
two henchmen 邪惡二獸 — 狡猾狐 (cunning fox) and 大灰熊 (big grey bear).

### 5.4 How it works: the hub, the map and the card battle
* **Hub — 雕仔小屋 / 雞仔小屋 ("Chick House"):** the prince's home in the game.
  From here you reach 龍虎榜 (leaderboards), 字謎咭/諺語咭 (the riddle and proverb
  cards), 成績表 and the farm itself; clicking furniture inside the house shows
  in-game scores and progress.
* **The farm map has 5 regions:** 魚塘 (fish pond), 牧場 (ranch), 農場 (farm),
  數字工場 (number workshop) and 年宵 (New Year fair) — 24 learning games in
  total, split 7 / 7 / 3 / 3 / 4 by region. Each region page states its teaching
  focus (e.g. 牧場 = 多感官教學, 農場 = 字詞教學, 魚塘 = 邏輯思維教學, 數字工場 =
  數學運算概念, 年宵 = 英語及數學教學).
* **Currency — 星之珠 (star pearls), 8 kinds:** 金 (metal), 木 (wood), 水 (water),
  火 (fire), 土 (earth), plus the special ones 大地 (earth-land), 雲火 (cloud-fire)
  and 光鑽 (light diamond). The five base pearls are earned by **passing levels**;
  the three special pearls are earned when the prince's **能量棒 (energy bar)
  reaches blue and fills up**.
* **Cards — 星之咭 (star cards):** pearl payments are exchanged with Fanda for
  cards; each draw needs a different combination of pearls, the star-card machine
  needs six pearls inserted, and the machine handle is pulled to draw. There are
  **28 cards**; each card carries a **point value in its top-left corner**
  representing attack/defence, and the higher the points the stronger both are.
  Cards are split into **普通咭 (normal)** and **首腦咭 (boss/leader)**; the player's
  own 首腦咭 is the little prince. A battle needs enough pearls to pay the
  entry, then the fight with the werewolf and his henchmen is **turn-based with
  dice**: the dice total for the round becomes the **行動值 (action points)**, and
  you may only put a card onto the field or attack if you have the action points.
  The printed turn sequence is 抽咭 (draw) → 擲骰 (roll) → 配置咭 (place cards) →
  攻擊 (attack) → 捨咭 (discard); the region screen also defines the 防護網
  (defence net), 準備位置 (staging positions) and 首腦咭 rules.
* **龍虎榜 (leaderboard):** your 積分 (points) ranking, star-pearl quantity
  ranking, star-card and word-card rankings, and so on; entering the **top three
  (三甲)** puts you on the 三甲排行榜 as recognition.
* **字謎咭 / 諺語咭 (riddle / proverb cards):** bought with earned points and then
  printable, so children can pose the riddles and proverbs to friends.
* **成績表:** newest / first / best score for each level of each game, plus the
  basic elements obtained, mystery energies, number of items owned and completion.

### 5.5 The 24 learning games

**牧場區域 — 多感官教學 (Ranch region — multi-sensory), 7 games**

| Game | Type | How you play | Levels |
|---|---|---|---|
| 豬豬相印 | visual discrimination | The prince stamps the pigs' bottoms — find the correct pattern and stamp it with the mouse. | 圖形 · 數字 · 英文字母 · 中文單字 · 中文詞語 |
| 牛牛疊趣 | visual discrimination (overlays) | Match the overlapping shadow on each cow and drag the cow into the right house. | 圖形 · 數字 · 英文字母 · 中文單字 |
| 雞仔連線 | visual memory (position) | Watch the chicks' order and positions; click the white dots in the same order. | 2條線 · 3-4條 · 4-5條 · 5-6條 · 6-7條線 |
| 礦石溫泉 (scan reading) | sentence expansion | Place word bombs into the right places in the sentence to expand it. | 形容詞 · 量詞 · 名詞/時間詞 |
| 森林樂隊 | auditory memory (order) | The forest band plays note sequences; remember the order and click the animals to play the same tune. | 動物叫聲 · 樂器 · 數字 · 英文字母 · 中文字 |
| 疾走馬車 | visual tracking | A carriage drives across the screen; identify the objects hidden by the crops and click the right answer. | 物品 · 數字 · 英文字母 · 中文單字 · 中文詞語 · 短句 |
| 牧場太鼓 | onomatopoeia | Drums at the festival carry onomatopoeic words (擬聲字); follow the prompt and strike the correct drum. | 難度低 · 難度中 · 難度高 |

**農場區域 — 字詞教學 (Farm region — word teaching), 7 games**

| Game | Type | How you play | Levels |
|---|---|---|---|
| 臨崖集果 | opposites & synonyms | Following the monkey's synonyms or the fox's opposites, find the matching answer (speed-based). | 速度慢 · 速度中 · 速度快 · 速度極快 |
| 擊鼠成字 / 射字成風 (scan reading) | character jigsaw | Shoot at the 部首/部件 shown on the 瞄準器 (sight) to assemble the correct character. | 速度慢 · 速度中 · 速度快 · 速度極快 |
| 配詞果樹 | word pairing | Climb the fruit tree with the mouse to reach the fruit that makes a correct word. | 速度慢 · 速度中 · 速度快 · 速度極快 |
| 拼字大塊田 | radical analysis | Find the radicals/components in the field that can build a character and drag them into the basket. | 左右 · 上下(下) · 上下(上) · 半包圍(一) · 半包圍(二) |
| 分柑同部 | radical discrimination | Before the crops fall off the conveyor belt, sort them into the right box by the radical of the character. | 速度慢 · 速度中 · 速度快 · 速度極快 |
| 筆順花田 | stroke order | Water the seeded holes with the mouse in the correct stroke order to write the character. | 初階 · 中階 · 高階 |
| 標點水管 | punctuation | Draw the right punctuation marks to join the broken pipes so the water reaches the field. | 逗號、句號 · 頓號、感嘆號 · 冒號、分號 · 問號、感嘆號 · 關引號、破折號及省略號 |

**魚塘區域 — 邏輯思維教學 (Fish-pond region — logical thinking), 3 games**

| Game | Type | How you play | Levels |
|---|---|---|---|
| 迷圖詠鵝 (scan reading) | picture guessing | Following the mother duck's raised clue, steer the duckling with the mouse and find the answer before the picture becomes fully clear. | 物品 · 圖形 · 字母 · 數字 · 中文單字 · 中文詞語 |
| 魚樂無同 | spot-the-difference | The net hauls up different items; within the time limit use the mouse to pick out the different one. | 6-10個物品 · 11-15個 · 16-20個 · 21-25個物品 |
| 釣魚求籤 (scan reading) | riddle game | The first half of a riddle appears on the bank; find its second half on the fish. | 難度低 · 難度中 · 難度高 |

**數字工場 — 數學運算概念 (Number workshop — maths concepts), 3 games**

| Game | Type | How you play | Levels |
|---|---|---|---|
| 數數牧場 | counting | The farm owner calls out how many animals are missing from the pen; collect exactly that number of animals with the mouse. | 兩種動物 · 三種動物 · 四種動物 |
| 乘法溫泉 | matrix quick-calculation | In the hot spring, work out the number of animals from their arrangement and click the answer as fast as you can. | 難度低 · 難度中 · 難度高 |
| 分果成籃 | division concepts | Divide the harvest by the basket's capacity to work out the minimum number of baskets needed. | 難度低 · 難度中 · 難度高 |

**年宵區域 — 英語及數學教學 (New Year fair region — English & maths), 4 games**

| Game | Type | How you play | Levels |
|---|---|---|---|
| 算式夾夾餅 | maths | The waffle-shop owner calls two numbers; in the time limit use the left/right keys to choose the right waffle machine and build the correct equation. | 整數:整數 · 分數:分數 · 帶分數:帶分數 · 小數:整數 · 分數:小數 · 假分數:小數 · 帶分數:小數 |
| 字串小魚池 | English vocabulary (memory) | Cast the net to string together the English letters carried by the fish and form different English words. | 5-7個字 · 8-10個字 |
| 變法魔術師 | English word-sort recognition | Within a set time, click in the tent the words that belong to the same category as the card the magician holds. | 1個詞類 · 2個詞類 · 3個詞類 |
| 快打煙火會 | English typing | English words rise with the fireworks; type them on the keyboard as fast as possible. | 2-4個字母 · 5-6個字母 · 7-15個字母 |

Aims as printed: attention, visual discrimination (figure/ground), visual
memory for position and order, auditory memory for sequence, stroke order and
character structure, radicals and components (their positions and meanings),
synonyms, antonyms, punctuation, onomatopoeia and riddle comprehension, plus
counting, multiplication, division, fractions/decimals/integers, and English
vocabulary, spelling and typing.

---

## 6. LPO — 《星願小王子》Online (星之國 Online)

### 6.1 Which game it is
The **online/multiplayer client** of the family: 《星願小王子》Online 系列, set in
**星之國 (the Kingdom of Stars)**, where each player lives as a citizen of the
kingdom. It is sold either as the complete collection **星之國 Online 全集** or as
nine separate episodes:

| Episode | Title |
|---|---|
| 第 1 集 | 魔法師之考驗 (The Mage's Test) |
| 第 2 集 | 奇幻玩具箱 (Fantasy Toy Box) |
| 第 3 集 | 暢遊海之島 (Cruising Sea Island) |
| 第 4 集 | 夢幻雪映國 (Dreamy Snowland) |
| 第 5 集 | 蟲林大樂章 (Grand Insect Symphony) |
| 第 6 集 | 勇闖失落遺跡 (Lost Ruins) |
| 第 7 集 | 聖誕夢工場 (Christmas Dream Factory) |
| 第 8 集 | 飛躍彩雲間 (Leaping the Clouds) |
| 第 9 集 | 疾風忍者村 / 疾風者村 (Ninja Village) |

Note the online client is the title this project calls **LPO**; the publisher's own
manual title is 《星願小王子》Online 全集 使用手冊.

### 6.2 Who it is for, and the design idea
The same primary-school literacy audience, but as a **shared online world**: the
publisher's page states the Online series was made to move the learning games onto
the internet so **students can play together online, cooperate on tasks and compete
with each other**, and that the interaction between students stimulates interest.
The manual is written for the home (personal) user: its first page is marked
**學校版使用者不用參考這頁** ("school-version users do not need this page").

### 6.3 The world you move around in
From the Online manual's 系統簡介 (system introduction) section:

* **家 (Home)** — where the player appears when entering the game. Contains
  **郵件** (mail: friends' messages, friend invitations and system notices, and
  you can write to friends), the **個人成績表** (personal report card showing each
  game's progress and score trend), **更改樣貌** (change appearance: eyebrows,
  eyes, nose, mouth, cheeks, ears, hair, and buying new expressions),
  **服飾與裝備** (clothes and equipment: drag items onto the character),
  **道具與裝備** (items and equipment) and **道具整理** (sorting weapons and items —
  with an 裝備袋 equipment bag and 貯物箱 storage box).
* **大街 (Main Street)** — the hub that leads to 市集 (market), the castle, the
  shops, 任務中心 (quest centre) and 傳送站 (teleport station), and back 回家
  (home).
* **市集 (Market)** — three shops: **服飾店** (clothes: tops, bottoms, shoes,
  headwear, hands), **道具店** (auxiliary/consumable items that help you last
  longer in the ruins) and **武器店** (weapons: staves, swords, axes, long-range
  and close-range weapons).
* **傳送站 (Teleport station)** — instead of walking slowly across the map you pick
  a destination and teleport there instantly.
* **任務中心 (Quest centre)** — the **任務主管** (quest master) offers many tricky
  quests; completing a quest gives a good reward. The ruins are entered through a
  fight with monsters, **only once per day**, so the manual advises equipping the
  weapons/items you want to take in.
* **城堡 (Castle)** — **告示板** (notice board with news about 星之國),
  **排行榜** (leaderboards: a 積分榜 score board that ranks the best score in each
  learning game, plus wealth, collection and star-crystal boards),
  **交友登記處** (friend registration: name lists to meet friends and adventure
  together) and the **皇家圖書館** (Royal Library, holding useful learning
  knowledge to help with the games).

### 6.4 Currency and progression
* **星星水晶 (star crystals) are the currency** — "in 星之國, star crystals are
  what you need to buy the objects you like." They are earned **by passing the
  learning games**: when you reach the target in a game, the crystal appears in
  that region's map, and **if your result is excellent you get extra crystals as a
  reward**.
* The **five basic crystals are 金, 木, 水, 火, 土 (metal, wood, water, fire,
  earth)**.
* Learning games are grouped by category icons on each card: 中 (Chinese), 英
  (English), 數 (maths), 感知 (perception), 邏輯思維 (logical thinking) and
  常識/其他 (general knowledge/other). Each card lists 目的 (aim), 關卡 (levels) and
  玩法 (how to play), so progression is per game, per level, with the results
  feeding the personal report card and the castle leaderboards.

### 6.5 The learning games, episode by episode
The aims below are the ones printed for each numbered learning game on the
publisher's page for the Online complete collection (`學習遊戲1` … `學習遊戲45`).
Level lists in the manual are given per game (examples in brackets).

**第 1 集 魔法師之考驗** — a magic world reached through the flying magic circle;
you search the magic forest for lost pearls, brew potions with the magic granny,
then fight the volcano dragon with flash bombs.
1. 魔法屠龍 — hand–eye coordination, stroke-order principles and stroke knowledge
   (mouse or handwriting pad; levels: 英文字母, 中文單字 1-5劃 / 6-10劃 / 11-16劃).
2. 快打魔法陣 — English typing and Chinese input (levels: 英文字母, 英文單字 2-3字 /
   4-5字 / 6-15字, 中文單字, 中文詞語).
3. 神秘藥室 — fast arithmetic and reverse thinking (levels: 兩整數加減 within 20 /
   within 100, 兩整數乘除 within 100 / within 200, 三數四則運算 with brackets,
   三數四則運算 without brackets).
4. 數字小魔怪 — visual tracking and number relationships (levels: 相同顏色,
   相同圖案, 單數或雙數, 相同公因數, 質數或非質數, 平方數或非平方數).
5. 分類迷雲陣 — Chinese/English vocabulary and classification, fast thinking and
   reactions (levels: 中文分類 / 英文分類 by number of categories, shallow to deep).

**第 2 集 奇幻玩具箱** — a toy kingdom: drive the toy train, help the toy
crocodile with its tooth, rescue the chess queen, try the pinball machine and
team up with the one-eyed monster.
6. 時態列車 — English tenses (present, past, future; levels: 10-12句 / 13-15句 /
   16-18句).
7. 牙牙學語 — English pronouns (levels by difficulty and number of answers).
8. 配數棋陣 — common ways of expressing numbers.
9. 面面珠機 — perimeter, area or volume (levels: 周界 · 面積 · 體積).
10. 地理小魔怪 — Hong Kong, China, the world, and famous places.

**第 3 集 暢遊海之島** — a seaside holiday island: shell-collecting races on the
beach, sailing, diving for treasure, coconut picking with the monkeys, and mixing
drinks in the juice house.
11. 同部搜集戰 — radicals and character meaning.
12. 聲母風帆賽 — Mandarin initials (聲母) grouped by place of articulation, for
    pronunciation accuracy.
13. 深海定向 — direction concepts in different expressions.
14. 拼音小猴子 — phonics, English pronunciation and spelling.
15. 七彩果汁屋 — logical thinking, data analysis and visual discrimination.

**第 4 集 夢幻雪映國** — an ice world: find ice bricks, reunite a penguin family,
light the match array for warmth, patch the igloo, skate and build snowmen.
16. 錯字冰磚 — common wrongly written characters (similar shape, sound or meaning,
    homophones).
17. 量詞尋親 — Chinese and English measure words (量詞) and noun meanings.
18. 智破火柴陣 — spatial control of lines, organisation, logical reasoning.
19. 七巧補冰屋 — geometric-figure sensitivity, spatial control and sensory-motor
    skill.
20. 名溜千史 — world famous people and general knowledge.

**第 5 集 蟲林大樂章** — a miniature insect world: water the buds, tend fruit with
the beetles, watch the animals, collect food for the ants and guide the worker
bees home.
21. 修辭採花 — rhetorical devices (修辭), sentence writing and composition.
22. 動物小算盤 — applying simple equations, four-rule arithmetic speed.
23. 水果聯想曲 — association skills, breadth of knowledge.
24. 螞步迷蹤 — direction and distance sense, 2-D visual memory.
25. 介詞衝蜂 — English prepositions and grammar.

**第 6 集 勇闖失落遺跡** — an ancient civilisation: gunpowder, stone-statue
fragments, a whip for treasures over lava, corridor murals with traps, floating
stones over the abyss, and an off-road jeep escape.
26. 深淵解文 — Chinese reading comprehension and hidden meaning.
27. 英語推理門 — English comparative vocabulary, logic and reasoning.
28. 解圖索寶 — reading statistical charts and finding data.
29. 分數謎牆 — fractions: concepts and operations.
30. 科學衝車 — wider knowledge, everyday science.

**第 7 集 聖誕夢工場** — Father Christmas's gift workshop.
31. 巧匠劃對稱 — geometric symmetry and axes of symmetry.
32. 點點樂韻 — musical scale and beat recognition, rhythm.
33. 普通話小屋 — Mandarin listening and positional vocabulary.
34. 拼音禮物站 — Mandarin pinyin finals and tones, distinguishing similar sounds.
35. 童夢英語 — English listening, descriptive phrases and imagination.

**第 8 集 飛躍彩雲間** — the sky: gather floating clouds, build a cloud castle,
unlock the rainbow chest in the rain clouds, fish for stars and collect hearts
with cupid's arrow.
36. 副詞雲蹤 — Chinese adverbs and their use in sentences.
37. 神算小飛象 — four-rule arithmetic and basic algebra.
38. 算出彩虹 — units and conversions.
39. 星河連接詞 — English conjunctions and adverbs.
40. 時空邱比特 — time and date formats and time calculations.

**第 9 集 疾風忍者村 / 疾風者村** — a ninja academy: practice ninjutsu on the
training posts, slip past the sentries by water, break through the defences over
the eaves, crack the secret door code and defeat the illusion boss to rescue the
captured princess.
41. 生物木樁陣 — living things, plants and animals.
42. 潛行六何法 — English question words (六何 = who/what/when/where/why/how) and
    question sentences.
43. 百科飛簷 — observation of everyday life and environment.
44. 聲調暗門 — Mandarin tones and tone-change rules.
45. 殘像相反詞 — English vocabulary and opposites.

---

## 7. Things the sources do NOT state

Listed so nothing here gets filled in from outside knowledge:

* Target age, school year or grade for **LP1, LP2, LP3 and LPO** (only LP4's shop
  page names a band).
* Version numbers, release dates, file sizes, or the number of levels in games
  whose cards say only "共有X關" (some LP2/LP3 cards give a fixed count; the rest
  list level themes).
* Any currency in **LPO** other than **星星水晶** (star crystals) — no coin,
  gold or cash name appears in the Online manual.
* Any **LPO** manual page on installation steps beyond the route above (the manual
  points to the home-edition browser downloads; the step-by-step install PDFs
  cover LP1/LP2/LP3 and Online separately, for PC and Mac).
* Whether the **17 stars / 20 games / 24 games** counts change with future
  updates — the manuals carry the disclaimer 所有內容以實際遊戲為準.
* A user manual for **LP1(R) 星夜重圓** (the manual index lists the title but
  provides no PDF link).
* Anything about the school/institution licence terms — the licence product pages
  exist, but their terms are not in the manuals summarised here.

---

## 8. Sources (exact URLs used)

**Manual index (the page the guide was asked to read):**
* `https://www.starwish-fair.com/pages/學習軟件使用手冊` — JavaScript-rendered;
  reachable HTML after rendering contains only the link list below.

**User manuals (scanned PDFs linked from that index):**
* `http://little-prince.com.hk/littleprince/Download/星願小王子使用手冊.pdf` (LP1)
* `http://little-prince.com.hk/littleprince/Download/星願外傳使用手冊.pdf` (LP2)
* `http://little-prince.com.hk/littleprince/Download/星願歷奇使用手冊.pdf` (LP3)
* `http://little-prince.com.hk/littleprince/Download/Online使用手冊.pdf` (LPO)
* `http://little-prince.com.hk/littleprince/Download/星願思語使用手冊.pdf` (LP4 — for context only)

**Publisher pages used for philosophy, story background, install steps and specs:**
* `https://www.starwish-fair.com/pages/產品的理念和特色`
* `https://www.starwish-fair.com/pages/《星願小王子》的由來`
* `https://www.starwish-fair.com/pages/軟件下載及安裝指引`
* `https://www.starwish-fair.com/pages/星願小王子` , `.../星願外傳` , `.../星願歷奇` , `.../星願小王子online` (category pages)
* Product pages: `https://www.starwish-fair.com/products/星願小王子1-全新雲端版`,
  `.../products/星願小王子ii---星願外傳`,
  `.../products/星願小王子iii---星願歷奇`,
  `.../products/星願小王子---星之國online全集`,
  `.../products/星願小王子iv---星願思語．星空聯盟`

**Installation step PDFs (linked from 軟件下載及安裝指引):**
* `http://www.little-prince.com.hk/littleprince/Download/星願小王子_星願外傳_星願歷奇_家用版軟件下載及安裝步驟--PC.pdf`
* `http://www.little-prince.com.hk/littleprince/Download/星願小王子_星願外傳_星願歷奇_家用版軟件下載及安裝步驟-MAC.pdf`
* `http://www.little-prince.com.hk/littleprince/Download/星願小王子Online_家用版軟件下載及安裝步驟-MAC.pdf`

**Home-edition software downloads named in those PDFs:**
* `http://www.little-prince.com.hk/littleprince/Download/LittlePrinceBrowserHome.zip` (PC, LP1-LP3)
* `http://www.little-prince.com.hk/littleprince/Download/LittlePrinceBrowserHome-Mac.zip` (Mac, LP1-LP3)
* `http://www.little-prince.com.hk/littleprince/Download/LittlePrinceBrowserOnline-Mac.zip` (Mac, Online)

**Login / registration endpoints named in the manuals:**
* `www.little-prince.com.hk/LP/personal` (LP1 cloud binding, login)
* `www.little-prince.com.hk/prince_online/` (Online registration, activation, play)
* Support contacts printed in the sources: `enquiry@little-prince.com.hk`,
  telephone `(852) 2557 9525` (site) and `3583 2665` (install guides).
