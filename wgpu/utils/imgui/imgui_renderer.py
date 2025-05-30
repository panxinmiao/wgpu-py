from imgui_bundle import imgui
import wgpu
from .imgui_backend import ImguiWgpuBackend


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

    # imgui changed its API between 1.5.2 and 1.6.0
    # But as of Dec 1, 2024, it is too early for us to force
    # users to use one specific version.
    # So we will support both versions for now with this small shim
    try:
        # Version 1.6.0 and above
        KEY_MAP_MOD = {
            "Shift": imgui.Key.mod_shift,
            "Control": imgui.Key.mod_ctrl,
            "Alt": imgui.Key.mod_alt,
            "Meta": imgui.Key.mod_super,
        }
    except AttributeError:
        # Version 1.2.1 to 1.5.2
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
        self._canvas_context = canvas.get_context("wgpu")

        # if the canvas is not configured, we configure it self.
        if self._canvas_context._config is None:
            if render_target_format is None:
                render_target_format = self._canvas_context.get_preferred_format(
                    device.adapter
                )
            self._canvas_context.configure(device=device, format=render_target_format)
        else:
            config_format = self._canvas_context._config.get("format")
            if (
                render_target_format is not None
                and config_format != render_target_format
            ):
                raise ValueError(
                    "The canvas is already configured with a different format."
                )
            render_target_format = config_format

        self._imgui_context = imgui.create_context()
        imgui.set_current_context(self._imgui_context)

        self._backend = ImguiWgpuBackend(device, render_target_format)

        self._backend.io.display_size = canvas.get_logical_size()
        scale = canvas.get_pixel_ratio()
        self._backend.io.display_framebuffer_scale = (scale, scale)

        canvas.add_event_handler(self._on_resize, "resize")
        canvas.add_event_handler(self._on_mouse_move, "pointer_move", order=-99)
        canvas.add_event_handler(
            self._on_mouse, "pointer_up", "pointer_down", order=-99
        )
        canvas.add_event_handler(self._on_key, "key_up", "key_down", order=-99)
        canvas.add_event_handler(self._on_wheel, "wheel", order=-99)
        canvas.add_event_handler(self._on_char_input, "char", order=-99)

        self._update_gui_function = None

    def set_gui(self, gui_updater: callable):
        """
        Set the gui update function that is called on every render cycle to update the GUI

        Arguments
        ---------
        gui_updater: callable
            GUI update function, must return imgui.ImDrawData: the draw data to
            render, this is usually obtained by calling ``imgui.get_draw_data()``

        Returns
        -------
        None

        """
        self._update_gui_function = gui_updater

    @property
    def imgui_context(self) -> imgui.internal.Context:
        """imgui context for this renderer"""
        return self._imgui_context

    @property
    def backend(self):
        """The backend instance used by this renderer."""
        return self._backend

    def render(self):
        """
        render the imgui draw data to the canvas
        """

        if self._update_gui_function is None:
            raise AttributeError(
                "Must set the GUI update function using set_gui() before calling render()"
            )

        imgui.set_current_context(self.imgui_context)
        draw_data = self._update_gui_function()

        pixel_ratio = self._canvas_context.canvas.get_pixel_ratio()
        lsize = self._canvas_context.canvas.get_logical_size()
        self._backend.io.display_framebuffer_scale = (pixel_ratio, pixel_ratio)
        self._backend.io.display_size = lsize

        command_encoder = self._backend._device.create_command_encoder()
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
        self._backend.render(draw_data, render_pass)
        render_pass.end()
        self._backend._device.queue.submit([command_encoder.finish()])

    def _on_resize(self, event):
        self._backend.io.display_size = (event["width"], event["height"])

    def _on_mouse_move(self, event):
        self._backend.io.add_mouse_pos_event(event["x"], event["y"])

        if self._backend.io.want_capture_mouse:
            event["stop_propagation"] = True

    def _on_mouse(self, event):
        event_type = event["event_type"]
        down = event_type == "pointer_down"
        self._backend.io.add_mouse_button_event(event["button"] - 1, down)

        if self._backend.io.want_capture_mouse:
            event["stop_propagation"] = True

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

        self._backend.io.add_key_event(key, down)

        if key_name in self.KEY_MAP_MOD:
            key = self.KEY_MAP_MOD[key_name]
            self._backend.io.add_key_event(key, down)

        if self._backend.io.want_capture_keyboard:
            event["stop_propagation"] = True

    def _on_wheel(self, event):
        self._backend.io.add_mouse_wheel_event(event["dx"] / 100, -event["dy"] / 100)

        if self._backend.io.want_capture_mouse:
            event["stop_propagation"] = True

    def _on_char_input(self, event):
        self._backend.io.add_input_characters_utf8(event["char_str"])

        if self._backend.io.want_text_input:
            event["stop_propagation"] = True
