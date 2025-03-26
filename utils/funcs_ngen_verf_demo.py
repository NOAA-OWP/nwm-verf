from rich.console import Console
from rich.syntax import Syntax
from pathlib import Path
import ruamel.yaml
from IPython.display import display, Image, HTML
from typing import Optional
import itertools
import time

def display_images(dir1:Path, 
                   plot_type: str, 
                   metrics: list[str], 
                   lead_times: Optional[list[str]]=None, 
                   datasets: Optional[list[str]]=None,
):

    # Generate filenames using list comprehension
    if plot_type == 'map':
        filenames = [f"map_{p1}_{p2}_{p3}.png" for p1, p2, p3 in itertools.product(metrics, lead_times, datasets)]
    elif plot_type == 'histogram':
        filenames = [f"hist_{p1}_{p2}.png" for p1, p2 in itertools.product(metrics, lead_times)]
    elif plot_type == 'boxplot':
        filenames = [f"boxplot_{p1}.png" for p1 in metrics]
    else:
        raise Exception(f'plot_type {plot_type} is not support')

    filenames = list(filenames)
    images = [Path(dir1, plot_type + 's', f1).resolve(strict=True) for f1 in filenames]
    if plot_type=='map':
        html_code = f"""
        <div style="text-align: center;">
            <img src="{images[0]}" style="width: 45%; display: inline-block; margin-right: 10px;">
            <img src="{images[1]}" style="width: 45%; display: inline-block;">
        </div>
        """
        display(HTML(html_code))
    else:
        #html = "".join(f'<img src="{img}" style="width: 500px; margin-right: 10px;">' for img in images)
        html = "".join(f'<img src="{img}?t={time.time()}" style="margin-right: 10px;">' for img in images)
        display(HTML(html))


def find_section_lines(yaml_file, section_name):
    start, end = None, None
    with open(yaml_file, "r") as file:
        lines = file.readlines()

    for i, line in enumerate(lines):
        #stripped = line.rstrip()
        if line.startswith(section_name + ":"):  # Find section start
            start = i + 1
        elif start is not None and line.startswith("#"):
            end = i - 1  # End when a new section starts
            break

    return start, end if end else len(lines)

def display_config(config_file:str, section:str):

    # make sure file exists
    file1 = Path(config_file)
    if not file1.exists():
        raise FileNotFoundError(file1)

    # Read the config file
    with open(file1, "r") as file:
        lines = file.readlines()

    # find start and end line numbers of the section
    start_line, end_line = find_section_lines(file1, section)

    # Extract the specific section
    selected_lines = "".join(lines[start_line-1 : end_line+1])  # Convert list back to string

    # Display using rich syntax highlighting
    console = Console()
    yaml_syntax = Syntax(selected_lines, "yaml", theme="monokai", line_numbers=True)
    console.print(yaml_syntax, soft_wrap = True)

def update_yaml_field(file_path, field_path, new_value):
    """
    Update a specific field in a YAML file.

    :param file_path: Path to the YAML file
    :param field_path: List representing the path to the field (e.g., ['general', 'location_set_name'])
    :param new_value: The new value to set for the field
    """
    yaml = ruamel.yaml.YAML()  # Use ruamel.yaml to preserve formatting and comments
    yaml.preserve_quotes = True  # Preserve formatting
    yaml.default_flow_style = None  # Allow inline lists

    with open(file_path, 'r', encoding='utf-8') as file:
        data = yaml.load(file)

    # Navigate to the correct field using the field_path
    field = data
    for key in field_path[:-1]:
        field = field.get(key, {})

    # Update the field value
    field[field_path[-1]] = new_value

    # Write the updated YAML back to the file
    with open(file_path, 'w', encoding='utf-8') as file:
        yaml.dump(data, file)