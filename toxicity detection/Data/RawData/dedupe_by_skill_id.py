import pandas as pd

# =========================
# 配置区：只改这里
# =========================
INPUT_CSV = "classifications.csv"      # 原始CSV路径
OUTPUT_CSV = "../ProcessData/classifications_deduped.csv" # 去重后CSV路径
DEDUP_KEY = "skill_id"                               # 按哪个字段去重
KEEP = "first"                                       # 保留第一条：first；保留最后一条：last
ENCODING = "utf-8"


# =========================
# 主逻辑
# =========================
def main() -> None:
    df = pd.read_csv(INPUT_CSV, encoding=ENCODING)

    if DEDUP_KEY not in df.columns:
        raise ValueError(f"CSV 中找不到去重字段: {DEDUP_KEY}\n当前字段为: {list(df.columns)}")

    original_count = len(df)
    deduped_df = df.drop_duplicates(subset=[DEDUP_KEY], keep=KEEP).copy()
    deduped_count = len(deduped_df)
    removed_count = original_count - deduped_count
    deduped_df.to_csv(OUTPUT_CSV, index=False, encoding=ENCODING)

    print(f"原始记录数: {original_count}")
    print(f"去重后记录数: {deduped_count}")
    print(f"删除重复记录数: {removed_count}")
    print(f"去重结果已保存到: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
