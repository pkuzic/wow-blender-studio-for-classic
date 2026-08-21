# WoW Blender Studio — for Classic (1.12)

A fork of WoW Blender Studio (`io_scene_wmo`) targeting the **vanilla 1.12 / Turtle** client.
Форк WoW Blender Studio (`io_scene_wmo`) под **ванильный клиент 1.12 / Turtle**.

## Classic-specific fixes in this fork / Отличия форка

| EN | RU |
|---|---|
| **Classic is the default** "Client version" for new scenes | **Classic — режим по умолчанию** («Client version») для новых сцен |
| **No phantom water**: Classic exports write `groupLiquid = 15` ("no liquid") for groups without a liquid mesh. On 1.12 a `0` there is treated as REAL water — the building floods and players swim | **Нет фантомной воды**: при Classic-экспорте у групп без жидкости пишется `groupLiquid = 15`. В 1.12 значение `0` читается как НАСТОЯЩАЯ вода — дом «затапливает» |
| **`Always draw` auto-stripped** on Classic export: on 1.12 the portal flood skips such groups — an interior with it stays sealed even WITH portals | **`Always draw` снимается автоматически** при Classic-экспорте: в 1.12 обход порталов пропускает такие группы — интерьер остаётся запечатан даже С порталами |
| **MOGI normalized** to the stock 1.12 subset (only the Indoor/Outdoor bit), like every Blizzard WMO | **MOGI нормализуется** до стокового вида 1.12 (только бит Indoor/Outdoor), как во всех WMO Blizzard |
| **Export lint for 1.12** (`wmo/classic_lint.py`): aborts/warns on portal mistakes before the file is written (see below) | **Линт экспорта под 1.12** (`wmo/classic_lint.py`): ошибки/предупреждения по порталам ДО записи файла (см. ниже) |

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
