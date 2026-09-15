import streamlit as st
from datetime import datetime, timezone, timedelta
import math
from lunar_python import Solar
import os
import json
import urllib.request
import zipfile
import opencc
from pypinyin import pinyin, Style

# ================= 康熙笔画与拆字模块 =================

# 1. 初始化简繁转换器
converter = opencc.OpenCC('s2t')

# 2. Unihan 数据库配置
UNIHAN_URL = "https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip"
ZIP_FILE = "Unihan.zip"
CACHE_FILE = "unihan_strokes.json"


def load_or_generate_strokes_db():
    """加载本地缓存，如果不存在则自动下载 Unihan 数据库并生成缓存"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    print("首次运行，正在下载 Unihan 笔画数据库（约 2MB）...")
    try:
        urllib.request.urlretrieve(UNIHAN_URL, ZIP_FILE)
    except Exception as e:
        print(f"下载失败: {e}，将使用空字典兜底。")
        return {}

    strokes_dict = {}
    print("正在解析数据库，请稍候...")
    with zipfile.ZipFile(ZIP_FILE, 'r') as z:
        # Unihan_IRGSources.txt 包含了汉字的总笔画数 (kTotalStrokes)
        with z.open('Unihan_IRGSources.txt') as f:
            for line in f:
                line = line.decode('utf-8')
                if line.startswith('#') or not line.strip():
                    continue
                parts = line.strip().split('\t')
                if len(parts) >= 3 and parts[1] == 'kTotalStrokes':
                    unicode_val = parts[0]  # 例如 U+4E00
                    strokes_val = parts[2].split(' ')[0]  # 取第一个数值
                    strokes_dict[unicode_val] = int(strokes_val)

    # 保存缓存，下次运行直接读取
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(strokes_dict, f, ensure_ascii=False)

    print(f"数据库准备就绪！共收录 {len(strokes_dict)} 个汉字的笔画数据。")
    return strokes_dict


# 加载数据库（首次运行会自动下载）
UNIHAN_STROKES = load_or_generate_strokes_db()


def get_accurate_strokes(char):
    """获取单个字的准确笔画数（优先繁体，兜底简体）"""
    # 1. 获取繁体字
    traditional_char = converter.convert(char)

    # 2. 优先查繁体字的 Unicode 编码对应的笔画
    unicode_trad = f"U+{ord(traditional_char):04X}"
    if unicode_trad in UNIHAN_STROKES:
        return UNIHAN_STROKES[unicode_trad]

    # 3. 如果繁体查不到，用简体字去查（兜底）
    unicode_simp = f"U+{ord(char):04X}"
    if unicode_simp in UNIHAN_STROKES:
        return UNIHAN_STROKES[unicode_simp]

    # 4. 终极兜底：如果数据库里真的没有（极罕见），返回 1 防止报错
    return 1


def get_character_info(char):
    """拆字模块：简繁转换 + 拼音 + 准确笔画数"""
    traditional_char = converter.convert(char)
    py = pinyin(char, style=Style.NORMAL)[0][0]

    # 获取准确笔画数
    strokes = get_accurate_strokes(char)

    return {
        "繁体字": traditional_char,
        "康熙笔画": strokes,
        "拼音": py
    }


# ================= 模块结束 =================


# ==========================================
# 1. 核心业务逻辑层
# ==========================================

def calculate_true_solar_time(beijing_time, longitude):
    """
    计算地方真太阳时（严格版）
    公式：真太阳时 = 北京时间 + 经度时差 + 均时差
    """
    standard_meridian = 120.0
    longitude_diff = longitude - standard_meridian

    # 均时差计算（更精确的公式）
    day_of_year = beijing_time.timetuple().tm_yday
    b = math.radians((360 / 365) * (day_of_year - 81))
    equation_of_time = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)

    # 真太阳时 = 北京时间 + 经度时差 + 均时差
    true_solar_time = beijing_time + timedelta(minutes=longitude_diff * 4 + equation_of_time)
    return true_solar_time


def get_ganzhi_from_true_solar_time(true_solar_time):
    """利用 lunar-python 库获取真太阳时对应的干支"""
    # 必须使用包含具体时间的 datetime 对象来初始化 Solar
    solar = Solar.fromDate(true_solar_time)
    lunar = solar.getLunar()

    # 获取日干支
    day_ganzhi = lunar.getDayInGanZhi()

    # 获取时干支（不需要传参，lunar 对象会自动根据时间计算）
    hour_ganzhi = lunar.getTimeZhi()

    return day_ganzhi, hour_ganzhi


def xiao_liu_ren_from_strokes(strokes, hour_zhi_index=None):
    """
    九宫小六壬起卦逻辑（基于康熙笔画或数字）
    九宫顺序：大安(0) -> 留连(1) -> 速喜(2) -> 赤口(3) -> 小吉(4) -> 空亡(5) -> 病符(6) -> 桃花(7) -> 天德(8)
    """
    # 九宫名称列表
    jiugong_names = ["大安", "留连", "速喜", "赤口", "小吉", "空亡", "病符", "桃花", "天德"]

    # 上卦（日传）：笔画数除以9取余
    day_index = strokes % 9
    if day_index == 0:
        day_index = 8
    day_name = jiugong_names[day_index]

    # 时传：如果提供了时辰索引，则结合时辰推算
    if hour_zhi_index is not None:
        hour_index = (day_index + hour_zhi_index + 1) % 9
        if hour_index == 0:
            hour_index = 8
    else:
        hour_index = day_index
    hour_name = jiugong_names[hour_index]

    return day_name, hour_name


# ==========================================
# 2. 你的核心断语字典 (日传+时传组合)
# ==========================================
CLASSIC_COMBO_JUDGMENT = {
    # ==========================================
    # 大安 (主静、主稳、主吉)
    # ==========================================
    ("大安", "大安"): "大安事事昌，求财在坤方，失物去不远，宅舍保安康。",
    ("大安", "留连"): "办事不周全，失物西北去，婚姻晚几天，凡事需迟延。",
    ("大安", "速喜"): "事事自己起，失物当日见，婚姻自己提，喜讯传千里。",
    ("大安", "赤口"): "办事不顺手，失物不用找，婚姻两分手，口舌惹烦恼。",
    ("大安", "小吉"): "事事从己及，失物不出门，婚姻成就地，和气自生春。",
    ("大安", "空亡"): "病人要上床，失物无踪影，事事不顺情，谋望总成空。",
    ("大安", "病符"): "身安病难侵，旧疾需静养，失物在西南，凡事求安稳。",
    ("大安", "桃花"): "人缘主稳定，感情慢热型，失物在东北，婚姻得安宁。",
    ("大安", "天德"): "贵人保平安，办事稳如山，失物西北找，婚姻得良缘。",

    # ==========================================
    # 留连 (主暗、主慢、主拖延)
    # ==========================================
    ("留连", "大安"): "办事两分张，婚姻有喜事，先苦后来甜，凡事莫心焦。",
    ("留连", "留连"): "留连事难成，求谋日未明，官事凡宜缓，去者未回程。",
    ("留连", "速喜"): "事事由自己，婚姻有成意，失物三天里，行人即当归。",
    ("留连", "赤口"): "病者死人口，失物准丢失，婚姻两分手，官非口舌有。",
    ("留连", "小吉"): "事事不用提，失物东南去，病者出人齐，凡事多迟疑。",
    ("留连", "空亡"): "病人准死亡，失物不见面，婚姻两分张，万事皆空亡。",
    ("留连", "病符"): "病情易反复，办事多拖延，失物难寻回，婚姻受牵连。",
    ("留连", "桃花"): "感情多纠葛，办事受牵绊，失物被遮挡，婚姻需细看。",
    ("留连", "天德"): "贵人虽相助，办事仍拖延，失物暂不见，婚姻需等待。",

    # ==========================================
    # 速喜 (主快、主吉、主喜讯)
    # ==========================================
    ("速喜", "大安"): "事事都平安，婚姻成全了，占病都相安，求财在南方。",
    ("速喜", "留连"): "婚姻不可言，失物无信息，病人有仙缘，凡事多周旋。",
    ("速喜", "速喜"): "速喜喜来临，求财向南行，失物申未午，逢人路上寻。",
    ("速喜", "赤口"): "自己往外走，失物往正北，婚姻得勤走，口舌莫多言。",
    ("速喜", "小吉"): "婚姻有人提，病人当天好，失物在家里，凡事皆顺意。",
    ("速喜", "空亡"): "婚姻有分张，病者积极治，失物不久见，先难后易成。",
    ("速喜", "病符"): "急病遇良医，办事有转机，失物快去找，婚姻有惊喜。",
    ("速喜", "桃花"): "桃花运旺盛，办事有人帮，失物快出现，婚姻喜洋洋。",
    ("速喜", "天德"): "贵人送喜讯，办事快如风，失物当日见，婚姻速成功。",

    # ==========================================
    # 赤口 (主凶、主口舌、主官非)
    # ==========================================
    ("赤口", "大安"): "办事险和难，失物东北找，婚姻指定难，凡事需谨慎。",
    ("赤口", "留连"): "办事有困难，行人在外走，失物不回还，官非口舌缠。",
    ("赤口", "速喜"): "婚姻在自己，失物有着落，办事官事起，先凶后见吉。",
    ("赤口", "赤口"): "赤口主口舌，官非切宜防，失物速速讨，行人有惊慌。",
    ("赤口", "小吉"): "办事自己提，婚姻不能成，失物无信息，凡事多争执。",
    ("赤口", "空亡"): "无病也上床，失物不用找，婚姻不能成，万事一场空。",
    ("赤口", "病符"): "病痛带口舌，办事多争执，失物遭损坏，婚姻起风波。",
    ("赤口", "桃花"): "桃花带烂缘，办事多口舌，失物因争丢，婚姻易破裂。",
    ("赤口", "天德"): "贵人解纷争，化险为夷平，失物有人送，婚姻得安宁。",

    # ==========================================
    # 小吉 (主小吉、主和合、主小成)
    # ==========================================
    ("小吉", "大安"): "事事两周全，婚姻当日定，失物自己损，凡事皆安稳。",
    ("小吉", "留连"): "事事有反还，婚姻有人破，失物上西南，凡事多周折。",
    ("小吉", "速喜"): "事事从头起，婚姻能成就，失物在院里，喜讯传千里。",
    ("小吉", "赤口"): "办事往外走，婚姻有难处，失物丢了手，口舌惹烦忧。",
    ("小吉", "小吉"): "小吉最吉昌，路上好商量，阴人来报喜，失物在坤方。",
    ("小吉", "空亡"): "病人不妥当，失物正东找，婚姻再想想，凡事多猜疑。",
    ("小吉", "病符"): "小病无大碍，办事勉强成，失物在角落，婚姻有小成。",
    ("小吉", "桃花"): "人缘尚可佳，办事有和气，失物在身旁，婚姻有小喜。",
    ("小吉", "天德"): "贵人暗相助，办事有小成，失物在西北，婚姻得小成。",

    # ==========================================
    # 空亡 (主空、主虚、主不吉)
    # ==========================================
    ("空亡", "大安"): "事事不周全，婚姻从和好，失物反复间，先难后易成。",
    ("空亡", "留连"): "办事处处难，婚姻重新定，失物永不还，凡事多拖延。",
    ("空亡", "速喜"): "事事怨自己，婚姻有一定，失物在家里，先凶后见吉。",
    ("空亡", "赤口"): "办事官非有，婚姻难定准，失物往远走，口舌惹烦忧。",
    ("空亡", "小吉"): "事事有猜疑，婚姻有喜事，失物回家里，凡事多周折。",
    ("空亡", "空亡"): "空亡事不祥，阴人少主张，求财无利益，行人有灾殃。",
    ("空亡", "病符"): "病体虚无力，办事一场空，失物无踪影，婚姻梦难成。",
    ("空亡", "桃花"): "桃花落空亡，感情虚一场，失物无处找，婚姻梦黄粱。",
    ("空亡", "天德"): "贵人难发力，办事落空虚，失物寻不见，婚姻叹分离。",

    # ==========================================
    # 病符 (主疾病、异常、治疗)
    # ==========================================
    ("病符", "大安"): "旧疾需静养，办事求稳当，失物在西南，婚姻需调养。",
    ("病符", "留连"): "病情易反复，办事多拖延，失物难寻回，婚姻受牵连。",
    ("病符", "速喜"): "急病遇良医，办事有转机，失物快去找，婚姻有惊喜。",
    ("病符", "赤口"): "病痛带口舌，办事多争执，失物遭损坏，婚姻起风波。",
    ("病符", "小吉"): "小病无大碍，办事勉强成，失物在角落，婚姻有小成。",
    ("病符", "空亡"): "病体虚无力，办事一场空，失物无踪影，婚姻梦难成。",
    ("病符", "病符"): "病符主灾殃，旧疾复发狂，办事多阻碍，需防身体伤。",
    ("病符", "桃花"): "因情致病，身心俱疲，失物在东北，婚姻多纠葛。",
    ("病符", "天德"): "病遇良医，逢凶化吉，办事有贵人，婚姻得安宁。",

    # ==========================================
    # 桃花 (主欲望、牵绊、异性)
    # ==========================================
    ("桃花", "大安"): "人缘主稳定，感情慢热型，失物在东北，婚姻得安宁。",
    ("桃花", "留连"): "感情多纠葛，办事受牵绊，失物被遮挡，婚姻需细看。",
    ("桃花", "速喜"): "桃花运旺盛，办事有人帮，失物快出现，婚姻喜洋洋。",
    ("桃花", "赤口"): "桃花带烂缘，办事多口舌，失物因争丢，婚姻易破裂。",
    ("桃花", "小吉"): "人缘尚可佳，办事有和气，失物在身旁，婚姻有小喜。",
    ("桃花", "空亡"): "桃花落空亡，感情虚一场，失物无处找，婚姻梦黄粱。",
    ("桃花", "病符"): "因情致病，身心俱疲，办事多隐患，婚姻需调理。",
    ("桃花", "桃花"): "桃花泛滥，感情复杂，办事多牵绊，婚姻需防变。",
    ("桃花", "天德"): "桃花遇贵人，感情得助力，失物有人送，婚姻成良缘。",

    # ==========================================
    # 天德 (主贵人、上司、福运)
    # ==========================================
    ("天德", "大安"): "贵人保平安，办事稳如山，失物西北找，婚姻得良缘。",
    ("天德", "留连"): "贵人虽相助，办事仍拖延，失物暂不见，婚姻需等待。",
    ("天德", "速喜"): "贵人送喜讯，办事快如风，失物当日见，婚姻速成功。",
    ("天德", "赤口"): "贵人解纷争，化险为夷平，失物有人送，婚姻得安宁。",
    ("天德", "小吉"): "贵人暗相助，办事有小成，失物在西北，婚姻得小成。",
    ("天德", "空亡"): "贵人难发力，办事落空虚，失物寻不见，婚姻叹分离。",
    ("天德", "病符"): "贵人寻良医，病情有转机，办事虽受阻，最终能化吉。",
    ("天德", "桃花"): "贵人牵红线，感情得良缘，办事有人帮，婚姻喜连连。",
    ("天德", "天德"): "双德护身，百事大吉，贵人重重助，万事皆顺意。",
}

# ==========================================
# 4. Streamlit 界面层
# ==========================================

st.set_page_config(page_title="九宫六壬排盘", page_icon="🔮", layout="wide")

st.title("🔮 九宫六壬排盘系统")
st.markdown("---")

# 侧边栏参数设置
with st.sidebar:
    st.header("⚙️ 参数设置")

    # 默认使用当前时间
    beijing_tz = timezone(timedelta(hours=8))
    default_time = datetime.now(beijing_tz)
    input_date = st.date_input("选择日期", value=default_time.date())
    input_time = st.time_input("选择时间", value=default_time.time())

    # 默认经度为广东汕头 (116.68°E)
    longitude = st.number_input("当地经度 (默认汕头 116.68°E)", value=116.68, format="%.2f")

    st.markdown("---")
    st.header("📖 拆字起卦")
    char_input = st.text_input("输入一个汉字（用于拆字起卦）", max_chars=1)

# 主界面逻辑
# 1. 初始化排盘状态（如果 session_state 中没有 'show_result'，则默认为 False）
if 'show_result' not in st.session_state:
    st.session_state.show_result = False

# 2. 点击按钮时，将状态修改为 True
if st.button("开始排盘"):
    st.session_state.show_result = True

# 3. 只要状态为 True，就持续展示排盘结果（切换下拉框时状态依然是 True，不会闪退）
if st.session_state.show_result:
    # ==========================================
    # 将之前所有的排盘计算和界面展示代码放在这里
    # ==========================================

    # 1. 计算真太阳时
    beijing_time = datetime.combine(input_date, input_time)
    true_solar_time = calculate_true_solar_time(beijing_time, longitude)

    # 2. 获取干支
    day_ganzhi, hour_ganzhi = get_ganzhi_from_true_solar_time(true_solar_time)

    # 3. 拆字模块
    char_info = None
    if char_input:
        char_info = get_character_info(char_input)

    # 4. 获取时辰索引
    hour_zhi_index = (true_solar_time.hour // 2) % 12
    if true_solar_time.hour == 23:
        hour_zhi_index = 0

    # 5. 排盘计算
    day_strokes = sum(ord(c) for c in day_ganzhi)
    day_name, hour_name = xiao_liu_ren_from_strokes(day_strokes, hour_zhi_index)

    char_day_name, char_hour_name = None, None
    if char_info:
        char_day_name, char_hour_name = xiao_liu_ren_from_strokes(char_info["康熙笔画"], hour_zhi_index)

    # ==========================================
    # 界面展示
    # ==========================================

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🕰️ 时日速断排盘")
        st.info(f"**真太阳时**：{true_solar_time.strftime('%Y-%m-%d %H:%M:%S')}")
        st.info(f"**日干支**：{day_ganzhi} | **时干支**：{hour_ganzhi}")

        st.markdown(f"### 落宫结果")
        st.success(f"**日传**：{day_name}  |  **时传**：{hour_name}")

        base_judgment = CLASSIC_COMBO_JUDGMENT.get((day_name, hour_name), "暂无断语")


        st.warning(base_judgment)

    with col2:
        st.subheader("📖 拆字起卦排盘")
        if char_info:
            st.info(f"**输入字**：{char_input} -> **繁体**：{char_info['繁体字']} | **拼音**：{char_info['拼音']}")
            st.info(f"**康熙笔画**：{char_info['康熙笔画']} 画")

            st.markdown(f"### 落宫结果")
            st.success(f"**日传**：{char_day_name}  |  **时传**：{char_hour_name}")

            char_base_judgment = CLASSIC_COMBO_JUDGMENT.get((char_day_name, char_hour_name), "暂无断语")


            st.warning(char_base_judgment)
        else:
            st.warning("请在左侧输入一个汉字进行拆字起卦。")
