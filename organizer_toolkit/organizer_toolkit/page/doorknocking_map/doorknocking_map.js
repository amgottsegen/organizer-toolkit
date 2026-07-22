frappe.pages['doorknocking-map'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Doorknocking Map',
		single_column: true
	});

	page.add_button("Regenerate Map", () => regenerate(iframe), {
		icon: "refresh",
	});

	const iframe = document.createElement("iframe");
	iframe.style.width = "100%";
	iframe.style.height = "80vh";
	iframe.style.border = "none";
	iframe.src = "/files/doorknocking_map.html";
	page.body.append(iframe);
}

function regenerate(iframe) {
	frappe.show_alert({ message: "Regenerating map...", indicator: "blue" });
	frappe.call({
		method: "organizer_toolkit.doorknocking.doorknocking_map.generate_doorknocking_map",
		callback: (r) => {
			if (r.message?.url) {
				// cache-bust so the iframe actually reloads the new file
				iframe.src = r.message.url + "?t=" + Date.now();
				frappe.show_alert({ message: "Map updated", indicator: "green" });
			}
		},
	});
}