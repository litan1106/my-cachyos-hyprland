--!nonstrict

shortcut.setLabel("Omarchy themes")
shortcut.setIcon("palette")

function onClick()
    noctalia.togglePanel("my-cachyos-hyprland/omarchy-themes:picker")
end

function onIpc()
    noctalia.togglePanel("my-cachyos-hyprland/omarchy-themes:picker")
end
