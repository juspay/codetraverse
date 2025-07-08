#!/bin/bash


check_uv(){
    if "$1" -m uv --version > /dev/null 2>&1; then 
        return 0
    else
        return 1
    fi
}

# Install UV
setup_uv(){
    # if check_uv "$1"; then
    #     echo "UV Already Installed"
    # else
        # curl -LsSf https://astral.sh/uv/install.sh | sh
        # source ~/.zshrc 2>/dev/null || true
        # source ~/.bash_profile 2>/dev/null || true
        "$1" -m venv "$2"/venv
        source "$2"/venv/bin/activate && pip install uv
        if ! check_uv "$1"; then
            echo ERROR - unable to install uv
            exit 1
        fi
    # fi
}

# Create Env
setup_env(){
    python_path="$1"
    codetraverse_dir="$2"
    setup_uv "$python_path" "$codetraverse_dir"
    echo $codetraverse_dir
    cd "$codetraverse_dir"
    "$python_path" -m uv init
    "$python_path" -m uv venv --python 3.13
    "$python_path" -m uv add -r "$codetraverse_dir"/codetraverse/requirements.txt
}

# Function call from CLI
if declare -f "$1" > /dev/null; then
  "$@"
else
  echo "'$1' is not a known function name" >&2
  exit 1
fi