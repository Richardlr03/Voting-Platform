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
});