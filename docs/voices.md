# Как говорят персонажи

> Регистр речи каждого героя с цитатами из оригинала. Открывать перед каждой итерацией.
> **Дописывать сюда** при уточнении манеры речи. Имена и термины — [`glossary.md`](glossary.md),
> согласованное с пользователем — [`decisions.md`](decisions.md).

Профили построены на **реальных репликах из скрипта**, а не по впечатлению от серии.
Атрибуция — по параметру кода `E101` в преамбуле сегмента, см. `tools/speakers.py`.

> **Статус: подтверждено пользователем 7 августа 2026, целиком и как есть** —
> с заметной стилизацией. Отвергнуты и сдержаннее, и ярче; обоснование —
> в [`decisions.md`](decisions.md). Контрасты между персонажами держат юмор дела,
> сглаживать их нельзя.

Посмотреть больше реплик персонажа:
`.venv\Scripts\python.exe tools\speakers.py --id 0002 --n 30`

## Главные

### `0000` — Майлз Эджворт (2947 реплик)

Прокурор, от его лица идёт и повествование. **Подчёркнуто книжная речь — согласовано.**
Полные конструкции, никаких разговорных срезов. В скобках — внутренний монолог,
там он позволяет себе яд.

**К Гамшу и Кей — на «ты», ко всем прочим — на «вы»** (решено 9 августа 2026).
Это его характеристика: «ты» достаётся ровно тем, кому он доверяет. В мыслях — та же
форма, плюс «ты» к Победину и Защитину, хотя вслух с ними он на «вы».
Полная таблица пар — в [`decisions.md`](decisions.md).

> The only incontrovertible fact here is that you don't know how to give a proper testimony.
> That's a very touching reason indeed. (And I don't believe a word of it.)
> Well, Mr. Carcerato is a boxer, so... three minutes would be my assumption.

Контраст его чопорности с болтовнёй Кей — рабочий источник юмора, сглаживать нельзя.

### `0002` — Кей Фарадей (1050)

Помощница, «Великий вор Ятагарасу». Подросток: восклицания, звукоподражания, простые
конструкции. **К Эджворту на «вы», но имя вставлять реже, чем в оригинале** — согласовано.

> You got it!
> Hey! Look at this weird piece of paper!
> *sniff sniff* Oof, smells like animals...
> Maybe the prisoners were making mud pies...?

Звуковые ремарки вроде `*sniff sniff*` сохранять как ремарки.

### `0009` — Верити Молотова (654)

Судья. Речь высокая, размеренная, с религиозным оттенком: она поклоняется Богине
правосудия. По-русски — торжественность без канцелярита.
Смех `Hah hah hah.` — сухой, с точкой, не с восклицанием. **Согласовано: «Ха-ха-ха.»**
(Раньше здесь стоял `Ooh hoo hoo hoo!` — ошибка, он принадлежит Лястраж,
см. [`decisions.md`](decisions.md).)

> Verity Gavèlle, at your service.
> She is all-merciful. You have but to confess, and you shall be saved.
> And those who were not have plausible alibis.

### `000B` — Эдди Защитин (480)

Адвокат защиты. Полная противоположность Эджворту: сленг, сокращения, панибратство,
французские вставки для шика. Здесь основной запас юмора дела.

> Enchanté, mademoiselle. And much obliged. Defense attorney Eddie Fender, at your service.
> I know, right? ... And that neckwear, obvs.
> It's always great to hang with a judicial compadre. C'mon, bring it in and chillax...
> Too much thinking fries my noggin.
> The Broncster called me the minute he was arrested.

По-русски: разговорная лексика, усечения, прозвища («Бронкстер»). Французские фразы
оставлять французскими — они и в оригинале иностранные.

### `0018` — Фифи Лястраж (349)

Начальница СИЗО. Приторно-любезная, сюсюкающая: `sweetie`, `darling`, «charming abode».
За приветливостью — жёсткость. Тюрьму зовёт `home` — «дом», сотрудников и заключённых
«семьёй»; это её постоянная нота, держать во всех вхождениях.
Смех `Hee hee!` — **согласовано: «Хи-хи!»**, а единственное `Ooh hoo hoo hoo!`
в `sce1_c1_03` — **«Ох-хо-хо-хо!»**

> Fifi Laguarde, by the way. Warden of this charming abode.
> Why yes, sweetie. Everything related to Kanis is with me now.
> And she's so adorable! So sweet! I could just gobble her right up!
> W-Well, of course I do, darling.

По-русски: «милочка», «дорогуша», уменьшительные суффиксы.

### `0019` — Фрэнк Видалл (300)

Заключённый, свидетель. Юлит, путается в показаниях, оправдывается.

> The name's Sahwit. Frank Sahwit.
> Well, I... I seem to remember being there, but... Maybe I was, maybe I wasn't...
> Why else would I have signed out a pair of rubber gloves!? For fun!?

### `0001` — детектив Гамшу (267)

Простодушный, служака, вечно голодный. Простые фразы, армейские отклики, самоирония.

> Roger that!
> EEEEEEEEK!
> Nnrgh... Oof, that's tight. Shouldn't have eaten that cake!
> Yeah... Guess I've still got a ways to go in the game of life...

По-русски: «Так точно!», просторечие, никакой книжности.

### `000A` — Юстас Победин (228)

Молодой прокурор. Спесь, самолюбование, постоянные «мои блестящие выводы». Смешон
именно серьёзностью, с которой себя подаёт.

> Hyeh heh heh!
> Then I'll just keep going. My brilliant deductions don't end there, you know!
> Hah! So my testimony's completely contradiction-free! I KNEW it!
> Look, it's simple: Since my first-rate investigation didn't turn up any weapon...

По-русски: превосходные степени, самодовольные вводные. Смех `Hyeh heh heh!` —
узнаваемая метка, **согласовано: «Хьех-хех-хех!»**, одинаково во всех вхождениях.

## Второстепенные

### `0015` — Бодхидхарма Канис (178)

Заключённый, буддийский монах. Речь степенная, с оборотами проповеди.
Смех `Kheh heh heh.` — **согласовано: «Кхех-хех-хех.»**

> I am Bodhidharma Kanis.
> Were I one to kill without rhyme or reason, I would still be free to recite sutras in peace out there.
> ...and still failed to find what they were looking for. I pray they weren't too disappointed. Kheh heh heh.

### `0017` — Рокко Карчерато (177)

Заключённый, боксёр. Уличная речь, проглоченные окончания: `gotta`, `woulda`, `hollerin'`.

> From the blue corner... it's Rocco "D-259" Carcerato!
> Hey, get the heck outta the ring if you're not gonna fight!
> Yeah, well, you don't even know the half of it, kid!

По-русски **жёсткое просторечие с искажённой орфографией — согласовано 7 августа 2026**:
«щас», «ниче», «чё», «грю», съеденные слоги. Не только лексика, но и написание слов:
у него в оригинале искажены сами слова, а не только словарь.

К Эджворту на «ты», обращение — **«начальник»** (`boss`, 21 раз). Выбрано сознательно
вместо нейтрального «шеф»: так заключённый и обращается к начальству, антураж включается
с полуслова. Медведь-напарник Teddy — **Мишутка**.

> Ниче милого в Мишутке нет. Он мне напарник, ясно?
> Т-Ты чё, начальник, головой поехал? Грю ж — ниче я не знаю!

### `0016` — Симеон Святов (141)

Пугливый, заикается, всё время извиняется. Заикание в оригинале — через дефис (`I-It's`,
`P-Please`); в русском тот же приём работает и его надо сохранять.

> I-It's Saint. S-Simeon Saint.
> P-Please don't hurt me! P-Please don't crush me with those h-h-huge arms!
> No "Objection!"? I-I knew it...!

### `001A` — циркачка (96)

Восторженная, сюсюкает над животными.

> Wow, what a cutie-patootie!
> And not just any story -- it's a love story! Isn't that dreamy?
> I'm sure I could get the little sweetie to open up for us!

### `0032` — безымянный заключённый (13 реплик)

Сосед Карчерато по блоку, звучит в `sce1_c0_05`, `sce1_c0_08` и `sce1_c1_m06_npc`.
Уличная речь того же покроя, что у Карчерато, но короче и без боксёрского антуража.
По-русски — просторечие со съеденными словами: «чё», «слыхал», «грит», «тож».

> Huh? Whaddaya want? I heard a scream. What of it?
> He's right! Neither of us coulda done it!
> The broken bracelet thing! 'Cause I want one too, ya hear!

### `002A` — охранник (63)

Служебные фразы, в панике заикается.

> Yes, miss? What can I do for you!?
> I-It's Kn-Kn-Knight! He, he... He's been k-k-killed!

### `0007` — Ши-Лонг Ланг (12 реплик)

Агент Интерпола из GK1. В деле 2 не присутствует: это воспоминания Эджворта
(`sce1_c1_08`) и встреча в `sce1_c1_0a`. Говорит резко, свысока, к Эджворту
на «ты» — не из близости, а от презрения; так же ему тыкают только Защитин
(панибратство) и Карчерато (блатная фамильярность), см. таблицу пар
в [`decisions.md`](decisions.md). Прокуроров и суды презирает открыто.

> Sorry, but the truth doesn't need the likes of you to distort it today!
> Hah. Our president doesn't have much faith in the efficacy of his own country's police force.
> It's funny, isn't it? I'm a real "lone wolf", now.

## Служебные слоты

| id | Что это |
|---|---|
| `003F` | Уведомления «данные записаны в органайзер» |
| `0041` | Плашки места и времени действия |
| `003D`, `003E` | Сборные слоты: под ними говорят разные эпизодические лица. Определять по контексту |
