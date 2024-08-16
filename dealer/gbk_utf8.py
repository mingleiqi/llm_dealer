def convert_gbk_to_utf8(input_file_path, output_file_path):
    with open(input_file_path, 'r', encoding='gbk') as input_file:
        content = input_file.read()

    with open(output_file_path, 'w', encoding='utf-8') as output_file:
        output_file.write(content)