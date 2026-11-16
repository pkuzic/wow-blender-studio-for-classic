# WoW Blender Studio — for Classic (1.12)

A fork of WoW Blender Studio (`io_scene_wmo`) targeting the **vanilla 1.12 / Turtle** client.
Форк WoW Blender Studio (`io_scene_wmo`) под **ванильный клиент 1.12 / Turtle**.

> **Install / Установка:** download **`io_scene_wmo-vX.Y.Z.zip`** from [Releases](https://github.com/pkuzic/wow-blender-studio-for-classic/releases/latest) (under *Assets*), then Blender 3.4 → Edit → Preferences → Add-ons → Install. **Not** "Code → Download ZIP" / "Source code": that copy has no update manifest.
> Скачайте **`io_scene_wmo-vX.Y.Z.zip`** со страницы [Releases](https://github.com/pkuzic/wow-blender-studio-for-classic/releases/latest) (раздел *Assets*), затем Blender 3.4 → Edit → Preferences → Add-ons → Install. **Не** «Code → Download ZIP» / «Source code»: в этой копии нет манифеста обновлений.

## Classic-specific fixes in this fork / Отличия форка

| EN | RU |
|---|---|
| **Classic is the default** "Client version" for new scenes | **Classic — режим по умолчанию** («Client version») для новых сцен |
| **No phantom water**: Classic exports write `groupLiquid = 15` ("no liquid") for groups without a liquid mesh. On 1.12 a `0` there is treated as REAL water — the building floods and players swim | **Нет фантомной воды**: при Classic-экспорте у групп без жидкости пишется `groupLiquid = 15`. В 1.12 значение `0` читается как НАСТОЯЩАЯ вода — дом «затапливает» |
| **`Always draw` auto-stripped** on Classic export: on 1.12 the portal flood skips such groups — an interior with it stays sealed even WITH portals | **`Always draw` снимается автоматически** при Classic-экспорте: в 1.12 обход порталов пропускает такие группы — интерьер остаётся запечатан даже С порталами |
| **MOGI normalized** to the stock 1.12 subset (only the Indoor/Outdoor bit), like every Blizzard WMO | **MOGI нормализуется** до стокового вида 1.12 (только бит Indoor/Outdoor), как во всех WMO Blizzard |
| **Export lint for 1.12** (`wmo/classic_lint.py`): aborts/warns on portal mistakes before the file is written (see below) | **Линт экспорта под 1.12** (`wmo/classic_lint.py`): ошибки/предупреждения по порталам ДО записи файла (см. ниже) |

## Model Browser / Браузер моделей

| EN | RU |
|---|---|
| **3D View → Sidebar (N) → WBS Browser.** Click **Load Model List** once: every `.m2` and `.wmo` in the active project's client is listed (cached, instant next time). | **3D View → боковая панель (N) → WBS Browser.** Один раз нажмите **Load Model List**: появится список всех `.m2` и `.wmo` клиента активного проекта (кэшируется, в следующий раз мгновенно). |
| **Search** by any part of the path (folder names too), filter **M2 / WMO**, and **Patch archives** (only custom content from `patch-*.mpq`) or **All archives**. The archive the game actually uses is shown next to each file. | **Поиск** по любой части пути (и по папкам), фильтр **M2 / WMO** и **Patch archives** (только своё содержимое из `patch-*.mpq`) или **All archives**. Рядом с файлом показан архив, из которого его берёт игра. |
| **Preview**: the selected model is rendered with its textures right in the panel; turn it with the arrows / *Turn* / *Tilt*. | **Превью**: выбранная модель рисуется с текстурами прямо в панели; вращение стрелками / *Turn* / *Tilt*. |
| **Textures**: each texture slot gets a short list with thumbnails: first the textures the game uses on this model (character **skins and hair** from CharSections, **creature skins** from CreatureDisplayInfo, **item textures** from ItemDisplayInfo, helms included), then recolours with the same name (*similar*). The **◀ ▶** arrows flip through that list; **Search all** opens a type-to-search list of every `.blp` in the model's folder (a texture picked there stays in the short list). The preview follows your choice. | **Текстуры**: у каждого слота короткий список с миниатюрами: сначала текстуры, которые игра использует на этой модели (**скины и волосы** персонажей из CharSections, **скины существ** из CreatureDisplayInfo, **текстуры предметов** из ItemDisplayInfo, включая шлемы), затем перекраски с тем же именем (*similar*). Стрелки **◀ ▶** листают этот список; **Search all** открывает поиск по всем `.blp` в папке модели (выбранная там текстура остаётся в коротком списке). Превью сразу показывает выбор. |
| **Import** brings the model into the scene with the chosen textures; **Apply Textures** swaps them on the M2 already in the scene. | **Import** загружает модель в сцену с выбранными текстурами; **Apply Textures** меняет текстуры у M2, уже стоящей в сцене. |
| **More in the preview**: tick which **geosets** to show (presets Default body / All / None); play **animations** (sequence list, Play/Pause, time slider); item models get their **ItemDisplayInfo** textures; **every archive** that holds the file is listed (the one the game uses is marked); **favourites** and **recent** filters; *(Everwood mode)* **Use HD (Upscale) textures** when the client has `Data\Upscale`. The model list now loads in the background with progress. | **Ещё в превью**: выбор **геосетов** (пресеты Default body / All / None); проигрывание **анимаций** (список, Play/Pause, ползунок времени); у предметов — текстуры из **ItemDisplayInfo**; список **всех архивов** с этим файлом (отмечен тот, что берёт игра); фильтры **Избранное** и **Недавние**; *(режим Everwood)* **Use HD (Upscale) textures**, если у клиента есть `Data\Upscale`. Список моделей теперь грузится в фоне с прогрессом. |

## Everwood mode / Режим Everwood

| EN | RU |
|---|---|
| **Preferences → Add-ons → WoW Blender Studio → Everwood mode** (off by default) shows the tools that only work with the Everwood client and its data: **.emorph** slider morphs, **HD (Upscale)** preview textures, and the Everwood client note in Send to test client. Leave it off for any other 1.12 client; everything else in this README works without it. | **Preferences → Add-ons → WoW Blender Studio → Everwood mode** (по умолчанию выключен) показывает инструменты, работающие только с клиентом и данными Everwood: морфы слайдеров **.emorph**, **HD-текстуры (Upscale)** в превью и пометку о клиенте Everwood в Send to test client. Для любого другого клиента 1.12 оставьте выключенным — всё остальное из этого README работает и без него. |

## Character tools / Инструменты для персонажей

| EN | RU |
|---|---|
| **3D View → Sidebar (N) → WBS Character.** **Safe Export** writes the ORIGINAL .m2 back with only the vertex positions (and their normals) you changed: geosets, vertex order, bones and sliders stay exactly as they were, so sculpted character models are safe to ship. Exporting an untouched import gives a byte-identical file. New vertices are refused (character topology must not change). | **3D View → боковая панель (N) → WBS Character.** **Safe Export** записывает ИСХОДНЫЙ .m2, заменяя только изменённые позиции вершин (и их нормали): геосеты, порядок вершин, кости и слайдеры остаются как были — скульпт персонажа безопасно отправлять в игру. Экспорт нетронутого импорта даёт байт-в-байт тот же файл. Новые вершины не принимаются (топологию персонажа менять нельзя). |
| *(Everwood mode)* **Load .emorph** turns our slider morphs into Blender shape keys (one per slider, negative shapes as `<name>.neg`); edit them or add new keys, then **Save .emorph**. Unedited files save back byte-identical; new keys get the next free id (100-126). | *(режим Everwood)* **Load .emorph** превращает морфы слайдеров в shape keys Blender (по одному на слайдер, отрицательные формы — `<имя>.neg`); правьте их или добавляйте новые, затем **Save .emorph**. Неизменённый файл сохраняется байт-в-байт; новые ключи получают следующий свободный id (100-126). |

## 1.12 checks and Send to test client / Проверки 1.12 и отправка в тестовый клиент

| EN | RU |
|---|---|
| Every **Classic M2 export** (and **File → Export → Check M2 for 1.12**) checks the written file: array bounds, index/vertex limits, bone palettes and weights, WotLK-only flags, missing textures, unknown animations, missing character geosets. Problems are listed; the file is kept. | Каждый **экспорт M2 в Classic** (и **File → Export → Check M2 for 1.12**) проверяет записанный файл: границы массивов, лимиты индексов/вершин, палитры костей и веса, флаги только для WotLK, отсутствующие текстуры, неизвестные анимации, недостающие геосеты персонажа. Проблемы выводятся списком; файл сохраняется. |
| **Scene properties → Send to test client** puts the exported model into the project's client: into the archive that currently wins for that file, after a confirmation. It refuses archives of 1.9 GB or more, locked archives (client running) and protected paths you list, backs the archive up once per session outside the client, and compacts it afterwards. Restart the client to see the change. | **Свойства сцены → Send to test client** кладёт экспортированную модель в клиент проекта — в архив, из которого игра сейчас берёт этот файл, после подтверждения. Отказывает для архивов от 1.9 ГБ, заблокированных архивов (клиент запущен) и путей из вашего списка защищённых, один раз за сессию делает копию архива вне клиента и затем сжимает его. Чтобы увидеть изменения, перезапустите клиент. |

## Tests / Тесты

| EN | RU |
|---|---|
| `py -3 tools/run_tests.py [filter] [--client PATH]` runs the GUI test suite in `tests/` (each test in its own Blender with a fresh config, on a second screen). Run it before every release. | `py -3 tools/run_tests.py [фильтр] [--client ПУТЬ]` запускает набор тестов из `tests/` (каждый тест — в своём Blender с чистым конфигом, на втором экране). Запускайте перед каждым релизом. |

## Updates / Обновления

| EN | RU |
|---|---|
| **Auto-update (v1.1.0+).** A few seconds after Blender starts (at most once a day) the add-on asks GitHub for the latest release of this fork. When a newer one exists you see **"Update available"** in the status bar, the *WoW Scene* panel and *Preferences > Add-ons > WoW Blender Studio > Updates*. | **Автообновление (v1.1.0+).** Через несколько секунд после запуска Blender (не чаще раза в день) аддон спрашивает GitHub о последнем релизе форка. Если есть новее — **«Update available»** появляется в строке состояния, в панели *WoW Scene* и в *Preferences > Add-ons > WoW Blender Studio > Updates*. |
| **Download Update** fetches it; **restart Blender** to finish (Windows locks the add-on's compiled modules while Blender runs, so the files are swapped at the next start). Only changed files are written; your `listfile.csv` and other local files are kept. | **Download Update** скачивает его; **перезапустите Blender**, чтобы завершить (пока Blender работает, Windows блокирует скомпилированные модули аддона, поэтому файлы заменяются при следующем запуске). Пишутся только изменённые файлы; ваш `listfile.csv` и прочие локальные файлы сохраняются. |
| Settings: *Check for updates automatically*, *Check every (days)* (0 = every start), *Custom update URL* (a JSON `{"version","url","notes","page"}` on our own server instead of GitHub). | Настройки: *Check for updates automatically*, *Check every (days)* (0 = при каждом запуске), *Custom update URL* (JSON `{"version","url","notes","page"}` на нашем сервере вместо GitHub). |
| A **git checkout** of the add-on is updated with `git pull --ff-only` (refused while it has local edits). | **Git-копия** аддона обновляется через `git pull --ff-only` (отказ, если есть локальные правки). |
| **Publishing a release (maintainers):** bump `bl_info["version"]`, run `py -3 tools/make_release.py`, then `gh release create v<X.Y.Z> dist/io_scene_wmo-v<X.Y.Z>.zip --title v<X.Y.Z> --notes "..."`. The tag must be newer than the installed version. | **Публикация релиза (для разработчиков):** поднять `bl_info["version"]`, запустить `py -3 tools/make_release.py`, затем `gh release create v<X.Y.Z> dist/io_scene_wmo-v<X.Y.Z>.zip --title v<X.Y.Z> --notes "..."`. Тег должен быть новее установленной версии. |

## The 1.12 sealed-interior problem / Проблема «запечатанного интерьера» в 1.12

**EN:** The 1.12 client renders WMO interiors strictly through portals: standing inside a
group, the outside world (terrain, sky, other models) is drawn **only** if a portal chain
leads from that group to an EXTERIOR group. No portals → flat void through every opening.
Later clients (3.3.5) are more forgiving, which is why WotLK-workflow habits produce
broken 1.12 WMOs. (Mechanism verified by disassembly of the 1.12.1/5875 client.)

**RU:** Клиент 1.12 рендерит интерьеры WMO строго через порталы: когда камера внутри
группы, внешний мир (террейн, небо, другие модели) рисуется **только** если из группы
есть портальная цепочка до EXTERIOR-группы. Нет порталов → пустота во всех проёмах.
Поздние клиенты (3.3.5) терпимее — поэтому привычки WotLK-пайплайна дают сломанные
WMO под 1.12. (Механизм подтверждён дизассемблированием клиента 1.12.1/5875.)

## Portal checklist for 1.12 / Чек-лист порталов под 1.12

1. **EN:** One flat quad mesh per opening (door, window, roof gap), slightly overlapping the
   wall edges. **RU:** Один плоский quad-меш на каждый проём (дверь, окно, дыра в крыше),
   с небольшим нахлёстом на края стены.
2. **EN:** Put every portal quad into the child collection named exactly **`Portals`** of the
   model collection. If it lives anywhere else it is silently NOT exported (the lint now warns).
   **RU:** Каждый портал — в дочернюю коллекцию с именем ровно **`Portals`**. Иначе он молча
   НЕ экспортируется (теперь линт предупредит).
3. **EN:** With the portal selected: Object Properties → **WMO Portal** → set **First group**
   and **Second group** (the two group meshes it connects). **RU:** Выделив портал: Object
   Properties → **WMO Portal** → назначить **First group** и **Second group**.
4. **EN:** Interior mesh goes in the **Indoor** collection; the shell in **Outdoor**.
   **RU:** Интерьер — в коллекцию **Indoor**; внешняя оболочка — в **Outdoor**.
5. **EN:** Never set **Always draw** on interior groups for 1.12 (auto-stripped on export).
   **RU:** Никогда не ставьте **Always draw** на интерьерные группы под 1.12 (снимается
   автоматически при экспорте).
6. **EN:** Leave Algorithm = Auto; if export reports "direction could not be computed", set
   Positive/Negative manually. **RU:** Algorithm = Auto; если экспорт сообщит «direction
   could not be computed» — выставьте Positive/Negative вручную.

## What the export lint checks / Что проверяет линт при экспорте

* half-linked portals (one group picker set) → **abort** with a readable message (any client
  version — this previously crashed the exporter); fully-unlinked portals → **abort** on Classic /
  портал с ОДНОЙ привязанной группой → **стоп** (любая версия — раньше это роняло экспортёр);
  портал совсем без групп → **стоп** на Classic;
* portal-like objects outside the `Portals` collection → warning (Classic) / порталы вне
  коллекции `Portals` → предупреждение (Classic);
* Indoor group with zero portals → warning "sealed room" / Indoor-группа без порталов →
  предупреждение «запечатанная комната»;
* `side=0` portal relations → **abort** (Classic) / связи портала с `side=0` → **стоп** (Classic);
* geometric openings between groups not covered by any portal (door/roof-seam detector) →
  warning with coordinates / геометрические проёмы между группами без портала → предупреждение
  с координатами;
* results shown in a popup + Info log after export / итог — в попапе и Info-логе после экспорта;
* post-export checks run for FULL exports only (PARTIAL skips groups and would produce false
  results) / пост-проверки работают только при ПОЛНОМ экспорте (PARTIAL пропускает группы).

## Not included / Чего нет

Retail-only data is excluded to keep the repo lean (`pywowlib/archives/listfile.csv`,
`pywowlib/wdbx/dbd/`) — re-add for retail CASC/DB2 features. Interior batch classification
(trans/int vs ext) lives in the compiled `wbs_kernel` and is unchanged.
Ретейл-данные исключены (`listfile.csv`, `dbd/`) — верните их для CASC/DB2. Классификация
батчей интерьера — в скомпилированном `wbs_kernel`, не менялась.
