// Custom JS for the AGM Voting Platform
console.log("AGM Voting Platform loaded");

// Auto-dismiss Bootstrap alerts after 3 seconds
document.addEventListener('DOMContentLoaded', function () {
	var alerts = document.querySelectorAll('.alert.alert-dismissible.show');
	alerts.forEach(function (alert) {
		setTimeout(function () {
			var bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
			bsAlert.close();
		}, 3000);
	});

	// Hide alerts that are visually associated with a form when the user starts typing.
	// This covers cases where the alert sits outside the <form> (e.g. above the form).
	document.querySelectorAll('form').forEach(function (form) {
		// listen on inputs inside the form
		var inputs = form.querySelectorAll('input, textarea, select');
		if (!inputs.length) return;

		var onFirstInput = function () {
			// Prefer a nearby container (card-body or the form's parent) to find related alerts
			var container = form.closest('.card-body') || form.parentElement || document;
			var relatedAlerts = container.querySelectorAll('.alert');
			relatedAlerts.forEach(function (alert) {
				try {
					var bs = bootstrap.Alert.getOrCreateInstance(alert);
					bs.close();
				} catch (e) {
					alert.remove();
				}
			});
		};

		inputs.forEach(function (input) {
			input.addEventListener('input', onFirstInput, { once: true });
		});
	});
});