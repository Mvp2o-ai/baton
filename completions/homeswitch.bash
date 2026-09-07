_complete()
{
  local cur="${COMP_WORDS[COMP_CWORD]}"
  local cmds="init clis models status model attach sidecar doctor sessions detach"
  if [[ ${COMP_CWORD} -eq 1 ]]; then
    COMPREPLY=( $(compgen -W "${cmds}" -- "${cur}") )
    return
  fi
  if [[ ${COMP_WORDS[1]} == clis ]]; then
    COMPREPLY=( $(compgen -W "list enable disable set refresh claude_code codex cursor" -- "${cur}") )
  elif [[ ${COMP_WORDS[1]} == model ]]; then
    COMPREPLY=( $(compgen -W "opus sonnet haiku gpt codex composer" -- "${cur}") )
  fi
}
complete -F _complete homeswitch
