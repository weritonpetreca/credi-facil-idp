import os

def inject_html_into_yaml():
    # Caminhos dos arquivos (ajuste se suas pastas forem diferentes)
    html_path = "a2i/task_template.html"
    yaml_path = "infrastructure/template.yaml"

    if not os.path.exists(html_path) or not os.path.exists(yaml_path):
        print("❌ Arquivos não encontrados. Verifique os caminhos.")
        return

    # 1. Lê o conteúdo do HTML real
    with open(html_path, "r", encoding="utf-8") as html_file:
        html_content = html_file.read()

    # 2. Formata o HTML para o padrão de bloco multilinha do YAML (recuo de 10 espaços)
    yaml_block_indicator = "|\n"
    indented_html = "".join([f"          {line}" for line in html_content.splitlines(keepends=True)])
    final_yaml_payload = yaml_block_indicator + indented_html

    # 3. Lê o template.yaml original
    with open(yaml_path, "r", encoding="utf-8") as yaml_file:
        yaml_content = yaml_file.read()

    # 4. Substitui o placeholder pelo HTML identado
    updated_yaml = yaml_content.replace('"HTML_TEMPLATE_PLACEHOLDER"', final_yaml_payload)

    # 5. Sobrescreve o template com a versão final pronta para o SAM
    with open(yaml_path, "w", encoding="utf-8") as yaml_file:
        yaml_file.write(updated_yaml)

    print("🚀 HTML injetado com sucesso no template.yaml!")

if __name__ == "__main__":
    inject_html_into_yaml()