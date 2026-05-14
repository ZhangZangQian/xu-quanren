#!/usr/bin/env python3
"""
紫微斗数排盘引擎 — 基于 iztro/py-iztro
适配许铨仁《紫微斗数命理学正解》宫星象三合一体系

用法:
  python3 paipan.py --solar "2000-8-16" --time 2 --gender 女
  python3 paipan.py --lunar "2000-7-17" --time 2 --gender 男
  python3 paipan.py --solar "1997-4-26" --time 1 --gender 男 --focus "婚姻"

输出: JSON 格式的完整命盘数据，含生年四化、飞宫、自化、大运
"""

import argparse
import json
import sys
from datetime import datetime

# 许铨仁体系四化表（与iztro默认一致，显式列出用于飞宫计算）
SIHUA_TABLE = {
    '甲': ['廉贞', '破军', '武曲', '太阳'],
    '乙': ['天机', '天梁', '紫微', '太阴'],
    '丙': ['天同', '天机', '文昌', '廉贞'],
    '丁': ['太阴', '天同', '天机', '巨门'],
    '戊': ['贪狼', '太阴', '右弼', '天机'],
    '己': ['武曲', '贪狼', '天梁', '文曲'],
    '庚': ['太阳', '武曲', '太阴', '天同'],
    '辛': ['巨门', '太阳', '文曲', '文昌'],
    '壬': ['天梁', '紫微', '左辅', '武曲'],
    '癸': ['破军', '巨门', '太阴', '贪狼'],
}

SIHUA_LABELS = ['禄', '权', '科', '忌']

# 宫位分类（许铨仁体系）
LIU_NEI = ['命宫', '财帛', '疾厄', '官禄', '田宅', '福德']  # 六内
LIU_WAI = ['子女', '夫妻', '兄弟', '仆役', '父母', '迁移']  # 六外
LIU_YANG = ['命宫', '财帛', '夫妻', '子女', '官禄', '福德']  # 六阳
LIU_YIN = ['兄弟', '父母', '疾厄', '田宅', '仆役', '迁移']  # 六阴
LIU_QIN = ['父母', '兄弟', '夫妻', '子女', '仆役', '迁移']  # 六亲
LIU_SHI = ['命宫', '财帛', '疾厄', '官禄', '田宅', '福德']  # 六事

# 对宫映射
OPPOSITE = {
    '命宫': '迁移', '迁移': '命宫',
    '财帛': '福德', '福德': '财帛',
    '兄弟': '仆役', '仆役': '兄弟',
    '夫妻': '官禄', '官禄': '夫妻',
    '子女': '田宅', '田宅': '子女',
    '疾厄': '父母', '父母': '疾厄',
}

# 十二宫序号（用于三方四正）
PALACE_ORDER = ['命宫', '兄弟', '夫妻', '子女', '财帛', '疾厄',
                '迁移', '仆役', '官禄', '田宅', '福德', '父母']


def get_palace_star_names(palace):
    """获取宫内所有星曜名称"""
    names = []
    for star in palace.major_stars:
        names.append(star.name)
    for star in palace.minor_stars:
        names.append(star.name)
    return names


def get_palace_star_details(palace):
    """获取宫内星曜详细信息（含四化）"""
    details = []
    for star in palace.major_stars:
        d = {'name': star.name, 'type': '主星', 'brightness': getattr(star, 'brightness', '')}
        if star.mutagen:
            d['mutagen'] = star.mutagen
        details.append(d)
    for star in palace.minor_stars:
        d = {'name': star.name, 'type': '辅星', 'brightness': getattr(star, 'brightness', '')}
        if star.mutagen:
            d['mutagen'] = star.mutagen
        details.append(d)
    return details


def calc_flying_sihua(palaces_dict, from_palace_name):
    """计算某宫宫干飞化到哪些宫
    
    返回: {禄: {star, palace, is_self}, 权: ..., 科: ..., 忌: ...}
    """
    from_palace = palaces_dict.get(from_palace_name)
    if not from_palace:
        return {}
    
    tiangan = from_palace['heavenly_stem']
    sihua_stars = SIHUA_TABLE.get(tiangan, [])
    
    result = {}
    for i, star_name in enumerate(sihua_stars):
        label = SIHUA_LABELS[i]
        for pname, pdata in palaces_dict.items():
            if star_name in pdata['star_names']:
                result[label] = {
                    'star': star_name,
                    'palace': pname,
                    'is_self_mutaged': (pname == from_palace_name)
                }
                break
    return result


def find_all_self_mutaged(palaces_dict):
    """找出所有自化象
    
    自化分两种（许铨仁体系）：
    1. 离心自化：本宫宫干飞化落回本宫的星辰（自化出）
    2. 向心自化（视同自化）：对宫宫干飞化落入本宫的星辰（自化入）
    """
    self_mu = []
    
    # 1. 离心自化：本宫宫干使本宫星辰化
    for pname, pdata in palaces_dict.items():
        tiangan = pdata['heavenly_stem']
        sihua_stars = SIHUA_TABLE.get(tiangan, [])
        for i, star_name in enumerate(sihua_stars):
            if star_name in pdata['star_names']:
                label = SIHUA_LABELS[i]
                self_mu.append({
                    'palace': pname,
                    'star': star_name,
                    'mutagen': label,
                    'tiangan': tiangan,
                    'direction': '离心',
                    'description': f"{pname}({tiangan}干): {star_name}离心自化{label}"
                })
    
    # 2. 向心自化（视同自化）：对宫宫干飞化落入本宫
    for pname, pdata in palaces_dict.items():
        opposite_name = OPPOSITE.get(pname)
        if not opposite_name or opposite_name not in palaces_dict:
            continue
        opp_data = palaces_dict[opposite_name]
        opp_tiangan = opp_data['heavenly_stem']
        opp_sihua_stars = SIHUA_TABLE.get(opp_tiangan, [])
        for i, star_name in enumerate(opp_sihua_stars):
            if star_name in pdata['star_names']:
                label = SIHUA_LABELS[i]
                self_mu.append({
                    'palace': pname,
                    'star': star_name,
                    'mutagen': label,
                    'tiangan': opp_tiangan,
                    'direction': '向心',
                    'from_palace': opposite_name,
                    'description': f"{pname}: {opposite_name}({opp_tiangan}干)飞入{star_name}化{label}→向心自化{label}"
                })
    
    return self_mu


def classify_palace(name):
    """宫位分类（许铨仁体系）"""
    classes = []
    if name in LIU_NEI:
        classes.append('六内')
    if name in LIU_WAI:
        classes.append('六外')
    if name in LIU_YANG:
        classes.append('六阳')
    if name in LIU_YIN:
        classes.append('六阴')
    if name in LIU_QIN:
        classes.append('六亲')
    if name in LIU_SHI:
        classes.append('六事')
    return classes


def sanfang_sizheng(palace_name):
    """计算三方四正宫位"""
    try:
        idx = PALACE_ORDER.index(palace_name)
    except ValueError:
        return []
    
    # 三方：本宫 + 间隔4 + 间隔8
    sanfang = [
        PALACE_ORDER[idx],
        PALACE_ORDER[(idx + 4) % 12],
        PALACE_ORDER[(idx + 8) % 12],
    ]
    # 四正：三方 + 对宫
    sizheng = sanfang + [OPPOSITE.get(palace_name, '')]
    return list(set(filter(None, sizheng)))


def build_chart(solar_date=None, lunar_date=None, time_index=2, gender='男',
                focus_date=None):
    """构建完整命盘数据"""
    from py_iztro import Astro
    
    astro = Astro()
    
    if solar_date:
        result = astro.by_solar(solar_date, time_index, gender, True, 'zh-CN')
    elif lunar_date:
        result = astro.by_lunar(lunar_date, time_index, gender, False, True, 'zh-CN')
    else:
        raise ValueError("必须提供 solar_date 或 lunar_date")
    
    # 基本信息提取
    nian_gan = result.chinese_date[0] if result.chinese_date else ''
    
    chart = {
        'basic': {
            'solar_date': result.solar_date,
            'lunar_date': result.lunar_date,
            'chinese_date': result.chinese_date,
            'nian_gan': nian_gan,
            'five_elements_class': result.five_elements_class,
            'soul': result.soul,
            'body': result.body,
            'gender': gender,
            'time_index': time_index,
        },
        'shengnian_sihua': {},  # 生年四化
        'palaces': {},  # 十二宫详情
        'flying_sihua': {},  # 各宫飞宫四化
        'self_mutaged': [],  # 自化象
        'decadal': {},  # 大运信息
    }
    
    # 生年四化
    if nian_gan in SIHUA_TABLE:
        for i, star_name in enumerate(SIHUA_TABLE[nian_gan]):
            label = SIHUA_LABELS[i]
            chart['shengnian_sihua'][label] = star_name
    
    # 十二宫详情
    palaces_dict = {}
    for palace in result.palaces:
        pdata = {
            'name': palace.name,
            'heavenly_stem': palace.heavenly_stem,
            'earthly_branch': palace.earthly_branch,
            'stars': get_palace_star_details(palace),
            'star_names': get_palace_star_names(palace),
            'major_stars': [s.name for s in palace.major_stars],
            'minor_stars': [s.name for s in palace.minor_stars],
            'classification': classify_palace(palace.name),
            'opposite': OPPOSITE.get(palace.name, ''),
            'sanfang_sizheng': sanfang_sizheng(palace.name),
            'is_body_palace': getattr(palace, 'is_body_palace', False),
            'is_original_palace': getattr(palace, 'is_original_palace', False),
            'decadal': {
                'range': f"{palace.decadal.range[0]}-{palace.decadal.range[1]}" if hasattr(palace, 'decadal') and palace.decadal and palace.decadal.range else '',
                'heavenly_stem': palace.decadal.heavenly_stem if hasattr(palace, 'decadal') and palace.decadal else '',
                'earthly_branch': palace.decadal.earthly_branch if hasattr(palace, 'decadal') and palace.decadal else '',
            },
        }
        
        # 生年四化象标注
        for star in palace.major_stars:
            if star.mutagen:
                pdata[f'生年化{star.mutagen}'] = star.name
        for star in palace.minor_stars:
            if star.mutagen:
                pdata[f'生年化{star.mutagen}'] = star.name
        
        palaces_dict[palace.name] = pdata
    
    chart['palaces'] = palaces_dict
    
    # 飞宫四化（十二宫各宫干飞化）
    for pname in palaces_dict:
        chart['flying_sihua'][pname] = calc_flying_sihua(palaces_dict, pname)
    
    # 自化象
    chart['self_mutaged'] = find_all_self_mutaged(palaces_dict)
    
    # 大运/流年
    if focus_date:
        try:
            horoscope = result.horoscope(focus_date)
            dec = horoscope.decadal
            year = horoscope.yearly
            
            chart['decadal'] = {
                'heavenly_stem': dec.heavenly_stem,
                'earthly_branch': dec.earthly_branch,
                'mutagen_stars': dec.mutagen,
                'palace_names': dec.palace_names,
            }
            chart['yearly'] = {
                'heavenly_stem': year.heavenly_stem,
                'earthly_branch': year.earthly_branch,
                'mutagen_stars': year.mutagen,
                'palace_names': year.palace_names,
            }
            
            # 大运天干四化
            if dec.heavenly_stem in SIHUA_TABLE:
                chart['decadal']['sihua'] = {}
                for i, star_name in enumerate(SIHUA_TABLE[dec.heavenly_stem]):
                    chart['decadal']['sihua'][SIHUA_LABELS[i]] = star_name
            
            # 流年天干四化
            if year.heavenly_stem in SIHUA_TABLE:
                chart['yearly']['sihua'] = {}
                for i, star_name in enumerate(SIHUA_TABLE[year.heavenly_stem]):
                    chart['yearly']['sihua'][SIHUA_LABELS[i]] = star_name
        except Exception as e:
            chart['decadal_error'] = str(e)
    
    return chart


def format_chart_text(chart):
    """将命盘数据格式化为许铨仁体系分析所需的文本摘要"""
    lines = []
    b = chart['basic']
    
    lines.append("=" * 60)
    lines.append(f"【命盘基本信息】")
    lines.append(f"  阳历: {b['solar_date']} | 阴历: {b['lunar_date']}")
    lines.append(f"  四柱: {b['chinese_date']} | 五行局: {b['five_elements_class']}")
    lines.append(f"  命主: {b['soul']} | 身主: {b['body']} | 性别: {b['gender']}")
    lines.append("=" * 60)
    
    # 生年四化
    sn = chart['shengnian_sihua']
    lines.append(f"\n【生年四化】({b['nian_gan']}干)")
    lines.append(f"  化禄: {sn.get('禄', '?')} | 化权: {sn.get('权', '?')} | 化科: {sn.get('科', '?')} | 化忌: {sn.get('忌', '?')}")
    
    # 十二宫
    lines.append(f"\n【十二宫职】")
    for pname in PALACE_ORDER:
        p = chart['palaces'].get(pname, {})
        major = ', '.join(p.get('major_stars', []))
        minor = ', '.join(p.get('minor_stars', [])[:3])
        
        # 生年四化标注
        sihua_tags = []
        for label in ['禄', '权', '科', '忌']:
            key = f'生年化{label}'
            if key in p:
                sihua_tags.append(f"化{label}")
        
        tag_str = f" [{','.join(sihua_tags)}]" if sihua_tags else ""
        class_str = '/'.join(p.get('classification', []))
        minor_str = f" | 辅:{minor}" if minor else ""
        
        lines.append(f"  {pname}({p.get('heavenly_stem','?')}{p.get('earthly_branch','?')}): {major}{tag_str} [{class_str}]{minor_str}")
    
    # 自化象
    if chart['self_mutaged']:
        lines.append(f"\n【自化象】")
        for item in chart['self_mutaged']:
            lines.append(f"  {item['description']}")
    
    # 大运
    if chart.get('decadal'):
        dec = chart['decadal']
        lines.append(f"\n【大运】{dec['heavenly_stem']}{dec['earthly_branch']}")
        if dec.get('sihua'):
            sh = dec['sihua']
            lines.append(f"  大运四化: 化禄:{sh.get('禄','?')} 化权:{sh.get('权','?')} 化科:{sh.get('科','?')} 化忌:{sh.get('忌','?')}")
    
    # 流年
    if chart.get('yearly'):
        year = chart['yearly']
        lines.append(f"\n【流年】{year['heavenly_stem']}{year['earthly_branch']}")
        if year.get('sihua'):
            sh = year['sihua']
            lines.append(f"  流年四化: 化禄:{sh.get('禄','?')} 化权:{sh.get('权','?')} 化科:{sh.get('科','?')} 化忌:{sh.get('忌','?')}")
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='紫微斗数排盘引擎（许铨仁体系）')
    parser.add_argument('--solar', type=str, help='阳历日期 YYYY-M-D')
    parser.add_argument('--lunar', type=str, help='阴历日期 YYYY-M-D')
    parser.add_argument('--time', type=int, required=True, help='时辰序号0-12（0=早子时,1=丑时...12=晚子时）')
    parser.add_argument('--gender', type=str, required=True, help='性别：男/女')
    parser.add_argument('--focus-date', type=str, help='关注日期（用于大运流年），格式YYYY-M-D')
    parser.add_argument('--json', action='store_true', help='输出完整JSON')
    parser.add_argument('--text', action='store_true', default=True, help='输出文本摘要（默认）')
    
    args = parser.parse_args()
    
    chart = build_chart(
        solar_date=args.solar,
        lunar_date=args.lunar,
        time_index=args.time,
        gender=args.gender,
        focus_date=args.focus_date,
    )
    
    if args.json:
        print(json.dumps(chart, ensure_ascii=False, indent=2))
    else:
        print(format_chart_text(chart))


if __name__ == '__main__':
    main()
