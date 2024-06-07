from imgui_bundle import imgui
import wgpu
from wgpu.utils.imgui_backend import ImguiWgpuBackend


class ImguiRenderer:
    KEY_MAP = {
        "ArrowDown": imgui.Key.down_arrow,
        "ArrowUp": imgui.Key.up_arrow,
        "ArrowLeft": imgui.Key.left_arrow,
        "ArrowRight": imgui.Key.right_arrow,
        "Backspace": imgui.Key.backspace,
        "CapsLock": imgui.Key.caps_lock,
        "Delete": imgui.Key.delete,
        "End": imgui.Key.end,
        "Enter": imgui.Key.enter,
        "Escape": imgui.Key.escape,
        "F1": imgui.Key.f1,
        "F2": imgui.Key.f2,
        "F3": imgui.Key.f3,
        "F4": imgui.Key.f4,
        "F5": imgui.Key.f5,
        "F6": imgui.Key.f6,
        "F7": imgui.Key.f7,
        "F8": imgui.Key.f8,
        "F9": imgui.Key.f9,
        "F10": imgui.Key.f10,
        "F11": imgui.Key.f11,
        "F12": imgui.Key.f12,
        "Home": imgui.Key.home,
        "Insert": imgui.Key.insert,
        # we don't know if it's left or right from wgpu-py, so we just use left
        "Alt": imgui.Key.left_alt,
        "Control": imgui.Key.left_ctrl,
        "Shift": imgui.Key.left_shift,
        "Meta": imgui.Key.left_super,
        "NumLock": imgui.Key.num_lock,
        "PageDown": imgui.Key.page_down,
        "PageUp": imgui.Key.page_up,
        "Pause": imgui.Key.pause,
        "PrintScreen": imgui.Key.print_screen,
        "ScrollLock": imgui.Key.scroll_lock,
        "Tab": imgui.Key.tab,
    }

    KEY_MAP_MOD = {
        "Shift": imgui.Key.im_gui_mod_shift,
        "Control": imgui.Key.im_gui_mod_ctrl,
        "Alt": imgui.Key.im_gui_mod_alt,
        "Meta": imgui.Key.im_gui_mod_super,
    }

    def __init__(
        self, device, canvas: wgpu.gui.WgpuCanvasBase, render_target_format=None
    ):

        # Prepare present context
        self._canvas_context = canvas.get_context()

        if render_target_format is None:
            # todo: not sure if this is the correct format, maybe we should expose it in the public API
            render_target_format = self._canvas_context.get_preferred_format(
                device.adapter
            )

        # if the canvas is not configured, we configure it self.
        # todo: maybe we should just raise an error if the canvas is not configured?
        if self._canvas_context._config is None:
            self._canvas_context.configure(device=device, format=render_target_format)

        imgui.create_context()

        self._beckend = ImguiWgpuBackend(device, render_target_format)

        self._beckend.io.display_size = canvas.get_logical_size()
        scale = canvas.get_pixel_ratio()
        self._beckend.io.display_framebuffer_scale = (scale, scale)

        canvas.add_event_handler(self._on_resize, "resize")
        canvas.add_event_handler(self._on_mouse_move, "pointer_move")
        canvas.add_event_handler(self._on_mouse, "pointer_up", "pointer_down")
        canvas.add_event_handler(self._on_key, "key_up", "key_down")
        canvas.add_event_handler(self._on_wheel, "wheel")

        # glfw.set_char_callback(canvas._window, self.on_char_input)

    def render(self, draw_data):
        command_encoder = self._beckend._device.create_command_encoder()
        current_texture_view = self._canvas_context.get_current_texture().create_view()
        render_pass = command_encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": current_texture_view,
                    "resolve_target": None,
                    "clear_value": (0, 0, 0, 1),
                    "load_op": wgpu.LoadOp.load,
                    "store_op": wgpu.StoreOp.store,
                }
            ],
        )
        self._beckend.render(draw_data, render_pass)
        render_pass.end()
        self._beckend._device.queue.submit([command_encoder.finish()])

    def _on_resize(self, event):
        self._beckend.io.display_size = (event["width"], event["height"])

    def _on_mouse_move(self, event):
        self._beckend.io.add_mouse_pos_event(event["x"], event["y"])

    def _on_mouse(self, event):
        event_type = event["event_type"]
        down = event_type == "pointer_down"
        self._beckend.io.add_mouse_button_event(event["button"] - 1, down)

    def _on_key(self, event):
        event_type = event["event_type"]
        down = event_type == "key_down"

        key_name = event["key"]
        if key_name in self.KEY_MAP:
            key = self.KEY_MAP[key_name]
        else:
            try:
                key = ord(key_name.lower())
                if key >= 48 and key <= 57:  # numbers 0-9
                    key = imgui.Key(imgui.Key._0.value + (key - 48))
                elif key >= 97 and key <= 122:  # letters a-z
                    key = imgui.Key(imgui.Key.a.value + (key - 97))
                else:
                    return  # Unknown key: {key_name}
            except ValueError:
                return  # Probably a special key that we don't have in our KEY_MAP

        self._beckend.io.add_key_event(key, down)

        if key_name in self.KEY_MAP_MOD:
            key = self.KEY_MAP_MOD[key_name]
            self._beckend.io.add_key_event(key, down)

    def _on_wheel(self, event):
        self._beckend.io.add_mouse_wheel_event(event["dx"] / 100, event["dy"] / 100)

    def _on_char_input(self, key):
        self._beckend.io.add_input_character(key)
