import pandas as pd


def count_null_values(csv_path, column_name):
    """
    统计 CSV 文件中某个字段的 Null 数量和占比
    """

    df = pd.read_csv(csv_path)

    if column_name not in df.columns:
        raise ValueError(f"字段不存在：{column_name}")

    null_values = ["", "Null", "NULL", "null", "None", "none", "NaN", "nan"]

    null_count = (
        df[column_name].isna() |
        df[column_name].astype(str).str.strip().isin(null_values)
    ).sum()

    total_count = len(df)

    print("========== Null 统计结果 ==========")
    print(f"CSV 文件：{csv_path}")
    print(f"字段名：{column_name}")
    print(f"总行数：{total_count}")
    print(f"Null 数量：{null_count}")
    print(f"Null 占比：{null_count / total_count:.2%}")


def check_field_values(csv_path, column_name, output_path=None):
    """
    查看 CSV 文件中某个字段有哪些取值，以及每个取值出现的次数
    """

    df = pd.read_csv(csv_path)

    if column_name not in df.columns:
        raise ValueError(f"字段不存在：{column_name}")

    value_counts = df[column_name].value_counts(dropna=False).reset_index()
    value_counts.columns = [column_name, "count"]

    print("========== 字段取值统计结果 ==========")
    print(f"CSV 文件：{csv_path}")
    print(f"字段名：{column_name}")
    print(f"不同取值数量：{len(value_counts)}")
    print(value_counts)

    if output_path:
        value_counts.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"字段取值统计结果已保存到：{output_path}")


if __name__ == "__main__":
    # ====== 配置区 ======
    csv_path = "skills_merged_with_decl_impl.csv"
    column_name = "source_plat"

    # ===================

    count_null_values(csv_path, column_name)

    print()

    check_field_values(csv_path, column_name)