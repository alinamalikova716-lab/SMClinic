"""Регрессионные тесты ядра по ТЗ (синтетические тексты).

Запуск:
    python scripts/test_core.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.processor import load_rules, process  # noqa: E402

TR, RO, UN = load_rules()


def run(text):
    return process(text, TR, RO, UN)


def show(name, res):
    trig = [(f["title"], f["attributes"].get("laterality")) for f in res["triggers"]]
    print(f"{name}: находок={len(res['findings'])} триггеров={trig}")
    return res


ok = True

# п.1.4 — негация только в клаузе
r = run("Кожа не изменена, подкожная клетчатка не изменена, в верхнем квадранте образование молочной железы 15 мм.")
show("1.4 клауза", r)
if not any("молочной железы" in f["title"] for f in r["triggers"]):
    print("   ✗ ожидался триггер образования"); ok = False

# п.1.3 — «нет операций» не глушит находку
r = run("В анамнезе нет операций, в щитовидной железе определяется узел 5 мм.")
show("1.3 нет-операций", r)
if not any("щитовидной" in f["title"] for f in r["triggers"]):
    print("   ✗ ожидался триггер узла щитовидной железы"); ok = False

# п.1.2 — собирать все BI-RADS, брать максимум
r = run("Справа BI-RADS 3. Слева BI-RADS 4. Молочные железы.")
show("1.2 birads", r)
prio = [x["priority"] for x in r["routes"]]
if "urgent" not in prio:
    print("   ✗ ожидался срочный маршрут (BI-RADS 4)"); ok = False

# п.1.1 — двусторонние находки не схлопываются
r = run("ПРАВАЯ МОЛОЧНАЯ ЖЕЛЕЗА: очаговое образование 10 мм. "
        "ЛЕВАЯ МОЛОЧНАЯ ЖЕЛЕЗА: очаговое образование 12 мм.")
show("1.1 двусторонние", r)
lat = sorted(f["attributes"].get("laterality") for f in r["findings"] if "очаговое" in f["title"].lower())
if lat != ["left", "right"]:
    print("   ✗ ожидались две находки: left и right"); ok = False

# «нельзя исключить» и ограничение оценки — это ТРИГГЕР (врач поставит диагноз)
r = run("В правой молочной железе определяется участок, нельзя исключить мастит.")
show("1.5 нельзя-исключить", r)
if not r["triggers"]:
    print("   ✗ ожидался триггер для формулировки сомнения"); ok = False

r = run("УЗИ молочных желез. В правой молочной железе участок. Заключение: нельзя исключить "
        "очаговое образование; оценка ограничена особенностями строения ткани.")
show("нельзя-исключить + ограничение", r)
if not r["triggers"] or any(f["status"] == "negated" for f in r["findings"]):
    print("   ✗ ожидался триггер, а не отрицание"); ok = False

# «без признаков» не триггер
r = run("В желчном пузыре без признаков конкрементов.")
show("без-патологии", r)
if r["triggers"]:
    print("   ✗ «без признаков» не должно быть триггером"); ok = False

# п.8 — бизнес-логика молочной железы и BI-RADS
BREAST = "УЗИ молочных желез. "


def expect(name, text, want_trigger):
    r = run(text)
    show(name, r)
    got = r["is_trigger"]
    if got != want_trigger:
        print(f"   ✗ ожидалось {'trigger' if want_trigger else 'нет trigger'}")
        return False
    return True


ok &= expect("BI-RADS 1", BREAST + "Заключение: уз-признаков патологии не выявлено. "
             "Категория BI-RADS 1 (правая молочная железа). Категория BI-RADS 1 (левая).", False)
ok &= expect("BI-RADS 2 + фоновые изменения (без кисты)",
             BREAST + "Диффузные изменения, фиброз, жировая инволюция, повышение эхогенности. "
             "Заключение: BI-RADS 2.", False)
ok &= expect("BI-RADS 3", BREAST + "Справа молочная железа. Заключение: образование, BI-RADS 3.", True)
ok &= expect("BI-RADS 4", BREAST + "Слева молочная железа. Заключение: BI-RADS 4.", True)
ok &= expect("BI-RADS 5", BREAST + "Слева молочная железа. Заключение: BI-RADS 5.", True)
ok &= expect("образований не выявлено", BREAST + "Заключение: объемных образований не выявлено. BI-RADS 2.", False)
ok &= expect("после маммопластики Br2", BREAST + "Заключение: состояние после маммопластики Br2.", False)
ok &= expect("без эхографически значимых изменений",
             "Поджелудочная железа и селезенка без эхографически значимых изменений.", False)
ok &= expect("нельзя исключить + BI-RADS 4 на фоне «патологии не выявлено»",
             "УЗИ молочных желез. Правая: очаговое образование. Заключение: "
             "нельзя исключить очаговое образование; BI-RADS 4 справа, BI-RADS 1 слева. "
             "Патологии не выявлено.", True)

# кисты: плановый маршрут к профильному специалисту
def expect_route(name, text, specialist, priority, want=True):
    r = run(text)
    show(name, r)
    if not r["triggers"]:
        if want:
            print("   ✗ ожидался триггер"); return False
        return True
    rt = r["routes"][0]
    good = rt["specialist"] == specialist and rt["priority"] == priority
    if not good:
        print(f"   ✗ ожидалось {specialist} / {priority}, получено {rt['specialist']} / {rt['priority']}")
    return good


ok &= expect_route("кисты МЖ, BI-RADS 2",
                   "УЗИ молочных желез. В обеих молочных железах единичные простые кисты до 4 мм. BI-RADS 2.",
                   "Маммолог", "planned")
ok &= expect_route("наботовы кисты шейки матки",
                   "УЗИ малого таза. В шейке матки определяются единичные наботовы кисты 3–5 мм.",
                   "Гинеколог", "planned")
ok &= expect("нет кист и образований, BI-RADS 1",
             "УЗИ молочных желез. Очаговых образований и кист не выявлено. BI-RADS 1.", False)

# ── три исправленные ошибки ────────────────────────────────────────────────
ok &= expect("печень: только «фиброзные изменения» без контекста",
             "Умеренные диффузные фиброзные изменения.", False)

r = run("Желчный пузырь: конкременты, взвесь и полиповидные образования не выявлены.")
show("перечень отрицаний", r)
_neg = {f["id"] for f in r["findings"] if f["status"] == "negated"}
if r["is_trigger"] or not {"cholelithiasis", "gallbladder_sludge", "gallbladder_polyp"} <= _neg:
    print("   ✗ ожидались negated: конкременты, взвесь, полиповидные образования"); ok = False

ok &= expect_route("наботовы кисты анэхогенные включения",
                   "В шейке матки определяются единичные анэхогенные включения 3–5 мм, "
                   "типичные для наботовых кист.", "Гинеколог", "planned")
ok &= expect("наботовы кисты не выявлены",
             "Наботовы кисты шейки матки не выявлены.", False)

print()
print("ИТОГ:", "все проверки пройдены" if ok else "есть ошибки")
sys.exit(0 if ok else 1)
