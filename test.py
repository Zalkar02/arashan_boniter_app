import subprocess
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def print_pdf(file_path, printer_name=None):
    command = ["lp"]
    if printer_name:
        command += ["-d", printer_name]
    command += ["-o", "fit-to-page=false", "-o", "scaling=100"]
    command.append(file_path)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0:
        print("✅ PDF отправлен на печать.")
    else:
        print("❌ Ошибка при печати:", result.stderr)

def mm(x):
    return x / 25.4 * 72

# ✅ Подключаем кириллический шрифт
pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/TTF/DejaVuSans.ttf'))

# 📐 Размер листа — альбомная ориентация A4
page_width, page_height = landscape(A4)

# ✅ Тестовые данные
data = {
    'Индивидуальный номер': '996000000999999',
    'Порода': 'Арашан',
    'Масть': 'Белая',
    'Кличка': 'Ак-Кулак',
    'Дата бонитировки': '08.08.25',
    'Возраст': '2',
    'Живая масса, кг': '112',
    'Высота в холке, см': '85',
    'Высота в крестце, см': '87',
    'Косая длина туловища, см': '98',
    'Ширина груди, см': '36',
    'Глубина груди, см': '50',
    'Ширина в маклаках, см': '28',
    'Обхват груди, см': '120',
    'Обхват курдюка, см': '100',
    'Форма курдюка': 'у',
    'Обхват пясти, см': '11',
    'Уши - Длина': '22',
    'Уши - Ширина': '9',
    'Голова - Длина': '32',
    'Голова - Ширина': '11',
    'Общая оценка': '90',
    'Величина': 'к',
    'Конституция': 'к',
    'Классность': '1',
    'Примечание': 'к',
}

# 📍 Координаты основных полей
coordinates = {
    'Индивидуальный номер': (mm(77), mm(168.5)),
    'Порода': (mm(26), mm(161.5)),
    'Масть': (mm(85), mm(161.5)),
    'Кличка': (mm(149), mm(161.5)),
    'Дата рождения': (mm(38), mm(153)),
    'Вес': (mm(80), mm(153)),
    'Место рождения': (mm(131), mm(153)),
}

# 📍 Координаты колонок бонитировки
col = {
    'Дата бонитировки': (mm(11), mm(29)),
    'Возраст': (mm(30), mm(40)),
    'Живая масса, кг': (mm(40), mm(50)),
    'Высота в холке, см': (mm(50), mm(61)),
    'Высота в крестце, см': (mm(61), mm(71)),
    'Косая длина туловища, см': (mm(71.5), mm(82)),
    'Ширина груди, см': (mm(82), mm(93)),
    'Глубина груди, см': (mm(93), mm(102)),
    'Ширина в маклаках, см': (mm(102), mm(112)),
    'Обхват груди, см': (mm(112), mm(122)),
    'Обхват курдюка, см': (mm(122), mm(133)),
    'Форма курдюка': (mm(133), mm(148)),
    'Обхват пясти, см': (mm(148), mm(157)),
    'Уши - Длина': (mm(157), mm(167)),
    'Уши - Ширина': (mm(167), mm(177)),
    'Голова - Длина': (mm(177), mm(187)),
    'Голова - Ширина': (mm(187), mm(197)),
    'Общая оценка': (mm(197), mm(208)),
    'Величина': (mm(208), mm(223)),
    'Конституция': (mm(223), mm(237.5)),
    'Классность': (mm(237.5), mm(252)),
    'Примечание': (mm(252), mm(268.5)),
    'Подпись бонитера': (mm(268.5), mm(285)),
}

row = [(mm(69), mm(79)), (mm(59), mm(69)), (mm(49), mm(59)), (mm(39), mm(49))]
row_father = (mm(27), mm(37))
row_mather = (mm(18), mm(27))


# 📝 Генерация PDF
c = canvas.Canvas("passport_baran_onepage.pdf", pagesize=(page_width, page_height))
c.setFont("DejaVuSans", 12)

# Основные поля
for field, (x, y) in coordinates.items():
    value = data.get(field, '')
    c.drawString(x, y + 3, str(value))

# Поля бонитировки — все значения в одной строке (можно сделать и в таблицу)
for field, (x1, x2) in col.items():
    value = data.get(field, '')
    y = row[0][0] + 10  # Строка в таблице (одна)
    c.drawString(x1, y, str(value))

c.save()
print("✅ Паспорт сгенерирован: passport_baran_onepage.pdf")
