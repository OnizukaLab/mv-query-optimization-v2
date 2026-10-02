import os
import re

input_path = "dataset/RED_SQL"
output_path = "Output/wvlet/"

#input_path = "dataset/wvlet_test"
#output_path = "Output/wvlet_test/"


# helper function that reformats queries
def sql_reformatter(sql_data):
    #   Whitespace and newline removal
    sql_data = sql_data.replace("     ", "") # removes 4 whitespaces
    sql_data = sql_data.replace("  ", "") # removes double whitespaces
    sql_data = sql_data.replace("\n", " ")

    # operator reformatting
    sql_data = sql_data.replace("SELECT", "select")
    pattern = re.compile("FROM", re.IGNORECASE)
    # need to ignore case if the operators are in lowercase
    sql_data = pattern.sub("\nfrom", sql_data)
    pattern = re.compile("WHERE", re.IGNORECASE)
    sql_data = pattern.sub("\nwhere", sql_data)
    pattern = re.compile("GROUP BY", re.IGNORECASE)
    sql_data = pattern.sub("\ngroup by", sql_data)
    pattern = re.compile("ORDER BY", re.IGNORECASE)
    sql_data = pattern.sub("\norder by", sql_data)

    # aggregation functions
    sql_data = sql_data.replace("MIN", "min")
    sql_data = sql_data.replace("MAX", "max")
    sql_data = sql_data.replace("COUNT", "count")
    sql_data = sql_data.replace("SUM", "sum")

    # Expressions
    sql_data = sql_data.replace('"', "`") # column names

    # Conditional Expressions
    sql_data = sql_data.replace("OR", "or")
    sql_data = sql_data.replace("AND", "and")
    sql_data = sql_data.replace("AS", "as")
    sql_data = sql_data.replace("IN", "in")
    sql_data = sql_data.replace("IS","is")
    sql_data = sql_data.replace("LIKE","like")
    sql_data = sql_data.replace("NOT","not")
    sql_data = sql_data.replace("NULL","null")

    sql_data = sql_data.replace("EXISTS","exists")
    sql_data = sql_data.replace("BETWEEN","between")

    # order by
    sql_data = sql_data.replace("ASC","asc")
    sql_data = sql_data.replace("DESC","desc")

    return sql_data

# sort key for query reordering
def sort_wvlet_operators(e):
    operator = e.split(" ")[0]
    # TODO : add where operators on groups
    match operator:
        case "from":
            res = 0
        case "where":
            res = 1
        case "group":
            res = 2
        case "select":
            res = 3
        case "order":
            res = 4
        case _:
            res = 10
    return res

# reorders queries to correspond to wvlet flow style query
def sql_reorder(sql_data):
    sql_data =  sql_data.split("\n")
    sql_data.sort(key=sort_wvlet_operators)
    sql_data = "\n".join(sql_data)
    return sql_data

def sql_to_wvlet(sql_data):
    result_query = sql_data
    result_query = sql_reformatter(result_query)
    result_query = sql_reorder(result_query)
    return result_query


if __name__ == "__main__":
    for file in os.listdir(input_path):
        if not file.endswith(".sql"):
            continue
        file_name = file.split(".")[0]
        with open(input_path + '/' + file_name + '.sql', 'r') as sql_file:
            sql_data = sql_file.read()
            sql_file.close()
        sql_data = sql_to_wvlet(sql_data)
        with open(output_path + file_name + '.wv', "w+") as out:
            out.write(sql_data)
   