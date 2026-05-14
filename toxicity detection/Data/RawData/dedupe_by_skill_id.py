import pandas as pd

# =========================
# 配置区：只改这里
# =========================
INPUT_CSV = "classifications.csv"                    # 原始 CSV 路径
OUTPUT_CSV = "../ProcessData/classifications_deduped.csv"  # 去重后 CSV 路径
ENCODING = "utf-8"
KEEP = "first"                                      # 保留第一条：first；保留最后一条：last

# 每个平台内部去重时使用的核心字段
DEDUP_KEY = "skill_id"
DEVELOPER_COLUMN = "developer"                       # 如果你的字段名不是 developer，在这里改

# 平台字段配置：
# 1. 如果你确定平台字段名，可以直接写成 "source_plat" / "platform" 等。
# 2. 如果设置为 None，程序会从 PLATFORM_COLUMN_CANDIDATES 中自动识别。
PLATFORM_COLUMN = None
PLATFORM_COLUMN_CANDIDATES = [
    "source_plat",
    "source_platform",
    "platform",
    "plat",
    "source",
    "platform_name",
]

# 是否清洗平台字段中的空值和前后空格。
# 注意：这里会直接写回平台字段，方便最终输出中的平台值保持一致。
NORMALIZE_PLATFORM_VALUE = True
UNKNOWN_PLATFORM_VALUE = "unknown_platform"

# 是否清洗 developer 字段用于去重。
# 注意：这里只生成临时去重键，不会改写最终输出 CSV 中的 developer 原始值。
NORMALIZE_DEVELOPER_FOR_DEDUP = True
UNKNOWN_DEVELOPER_VALUE = "unknown_developer"

# 是否在最终输出前清洗 skill_id：
# 例如 "xxx/yyy/skill-name" -> "skill-name"
# 注意：这里保持你之前的逻辑，先按原始 skill_id + developer 在平台内部去重，再清洗最终输出中的 skill_id。
NORMALIZE_SKILL_ID = True
SKILL_ID_COLUMN = "skill_id"

# 临时列名，避免和原 CSV 字段冲突。
_DEDUP_PLATFORM_COLUMN = "__dedup_platform__"
_DEDUP_DEVELOPER_COLUMN = "__dedup_developer__"


# =========================
# 工具函数
# =========================
def normalize_skill_id(value):
    """
    将 skill_id 按 / 切分，只保留最后一段。
    例如：
        "a/b/c" -> "c"
        "c"     -> "c"
    对空值保持原样。
    """
    if pd.isna(value):
        return value

    value = str(value).strip()
    if not value:
        return value

    # 先去掉末尾多余的 /，避免 "a/b/c/" 被切成空字符串
    value = value.rstrip("/")
    return value.split("/")[-1]


def detect_platform_column(df: pd.DataFrame) -> str:
    """
    自动识别 CSV 中的平台字段。
    如果 PLATFORM_COLUMN 被显式指定，则优先使用该字段。
    """
    if PLATFORM_COLUMN is not None:
        if PLATFORM_COLUMN not in df.columns:
            raise ValueError(
                f"CSV 中找不到指定的平台字段: {PLATFORM_COLUMN}\n"
                f"当前字段为: {list(df.columns)}"
            )
        return PLATFORM_COLUMN

    for column in PLATFORM_COLUMN_CANDIDATES:
        if column in df.columns:
            return column

    raise ValueError(
        "CSV 中找不到平台字段。\n"
        f"已尝试自动识别这些字段: {PLATFORM_COLUMN_CANDIDATES}\n"
        f"当前字段为: {list(df.columns)}\n"
        "请在配置区手动设置 PLATFORM_COLUMN。"
    )


def normalize_key_series(series: pd.Series, unknown_value: str) -> pd.Series:
    """
    用于构建去重键的通用清洗逻辑：
    - 转为字符串类型并去除前后空格；
    - 将空值、空字符串、nan/none/null 替换为指定的 unknown_value。

    这样可以避免 developer 为 NULL 时造成去重逻辑不稳定。
    """
    normalized = series.astype("string").str.strip()
    invalid_mask = (
        normalized.isna()
        | normalized.eq("")
        | normalized.str.lower().isin(["nan", "none", "null"])
    )
    normalized = normalized.mask(invalid_mask, unknown_value)
    return normalized


def build_platform_stats(
    df: pd.DataFrame,
    deduped_df: pd.DataFrame,
    platform_column: str,
) -> pd.DataFrame:
    """
    生成每个平台的去重统计，方便检查是否按平台内部去重。
    """
    before = df.groupby(platform_column, dropna=False).size().rename("original_count")
    after = deduped_df.groupby(platform_column, dropna=False).size().rename("deduped_count")

    stats = pd.concat([before, after], axis=1).fillna(0).astype(int)
    stats["removed_count"] = stats["original_count"] - stats["deduped_count"]
    stats = stats.reset_index().sort_values(by="removed_count", ascending=False)
    return stats


# =========================
# 主逻辑
# =========================
def main() -> None:
    df = pd.read_csv(INPUT_CSV, encoding=ENCODING)

    required_columns = [DEDUP_KEY, DEVELOPER_COLUMN]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(
            f"CSV 中找不到必要字段: {missing_columns}\n"
            f"当前字段为: {list(df.columns)}"
        )

    if NORMALIZE_SKILL_ID and SKILL_ID_COLUMN not in df.columns:
        raise ValueError(f"CSV 中找不到 skill_id 清洗字段: {SKILL_ID_COLUMN}\n当前字段为: {list(df.columns)}")

    platform_column = detect_platform_column(df)

    if NORMALIZE_PLATFORM_VALUE:
        df[platform_column] = normalize_key_series(df[platform_column], UNKNOWN_PLATFORM_VALUE)

    # 构造临时去重键。
    # 平台字段可以直接使用清洗后的值；developer 使用临时列，避免改写原始 developer 内容。
    df[_DEDUP_PLATFORM_COLUMN] = normalize_key_series(df[platform_column], UNKNOWN_PLATFORM_VALUE)

    if NORMALIZE_DEVELOPER_FOR_DEDUP:
        df[_DEDUP_DEVELOPER_COLUMN] = normalize_key_series(df[DEVELOPER_COLUMN], UNKNOWN_DEVELOPER_VALUE)
    else:
        df[_DEDUP_DEVELOPER_COLUMN] = df[DEVELOPER_COLUMN]

    original_count = len(df)

    # 核心逻辑：在每个平台内部，按 skill_id + developer 联合去重。
    # 注意：developer 为 NULL / nan / 空字符串时，会统一映射成 unknown_developer 参与去重；
    #      因此同一平台内，同一 skill_id 且 developer 同为缺失的记录会被视为重复。
    #      但 developer 缺失和 developer 有明确值的记录不会互相去重。
    dedup_subset = [_DEDUP_PLATFORM_COLUMN, DEDUP_KEY, _DEDUP_DEVELOPER_COLUMN]
    deduped_df = df.drop_duplicates(subset=dedup_subset, keep=KEEP).copy()

    # 去掉临时列，避免污染最终输出。
    deduped_df = deduped_df.drop(columns=[_DEDUP_PLATFORM_COLUMN, _DEDUP_DEVELOPER_COLUMN])

    # 再处理最终输出中的 skill_id，只保留 / 后最后一段。
    if NORMALIZE_SKILL_ID:
        deduped_df[SKILL_ID_COLUMN] = deduped_df[SKILL_ID_COLUMN].apply(normalize_skill_id)

    deduped_count = len(deduped_df)
    removed_count = original_count - deduped_count

    deduped_df.to_csv(OUTPUT_CSV, index=False, encoding=ENCODING)

    platform_stats = build_platform_stats(df, deduped_df, platform_column)

    print(f"原始记录数: {original_count}")
    print(f"去重后记录数: {deduped_count}")
    print(f"删除重复记录数: {removed_count}")
    print(f"平台字段: {platform_column}")
    print(f"平台内去重键: [平台字段, {DEDUP_KEY}, {DEVELOPER_COLUMN}]")
    print(f"developer 缺失值去重占位: {UNKNOWN_DEVELOPER_VALUE}")
    print(f"是否清洗平台字段: {NORMALIZE_PLATFORM_VALUE}")
    print(f"是否用规范化 developer 去重: {NORMALIZE_DEVELOPER_FOR_DEDUP}")
    print(f"是否清洗 skill_id: {NORMALIZE_SKILL_ID}")
    print(f"去重结果已保存到: {OUTPUT_CSV}")

    print("\n各平台去重统计:")
    print(platform_stats.to_string(index=False))


if __name__ == "__main__":
    main()
