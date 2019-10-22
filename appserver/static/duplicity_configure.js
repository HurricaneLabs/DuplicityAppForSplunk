require([
    "underscore",
    "jquery",
    "splunkjs/mvc",
    "splunkjs/ready!",
    "splunkjs/mvc/simplexml/ready!",
], function(_, $, mvc) {
    var service = mvc.createService({ owner: "nobody" });
    var defaultTokenModel = mvc.Components.getInstance("default", {create: true});
    var submittedTokenModel = mvc.Components.getInstance("submitted", {create: true});

    function setToken(name, value) {
        defaultTokenModel.set(name, value);
        submittedTokenModel.set(name, value);
    }

    function unsetToken(name) {
        defaultTokenModel.unset(name);
        submittedTokenModel.unset(name);
    }

    _.each($(".duplicity-input"), function (value, key, list) {
        var tokenName = $(value).data("token");
        // console.log($(value));
        // console.log(tokenName);

        if (tokenName) {
            defaultTokenModel.on("change:" + tokenName, function(oldValue, newValue) {
                $(value)[0].value = newValue;
            });
        }
    });

    service.request(
        "configs/conf-inputs/duplicity%3A%2F%2Fbackup",
        "GET",
        null,
        null,
        null,
        null,
        null
    ).done(function(resp) {
        // console.log(resp);
        data = JSON.parse(resp);
        config = data.entry[0].content;

        _.each($(".duplicity-input"), function (value, key, list) {
            var tokenName = $(value).data("token");

            if (tokenName) {
                var tokenValue = config[tokenName];
                if (tokenValue !== undefined) {
                    if (tokenName == "whitelist" || tokenName == "blacklist") {
                        tokenValue = tokenValue.replace(";", "\n");
                    }
                    setToken(tokenName, tokenValue);
                }
            }
        });
    });

    $("body").on("click", ".duplicity-configure-form .save-button", function(e) {
        var payload = {}

        _.each($(".duplicity-input"), function (value, key, list) {
            var tokenName = $(value).data("token");
            var tokenValue = $(value)[0].value;

            if (tokenName) {
                if (tokenName == "whitelist" || tokenName == "blacklist") {
                    tokenValue = tokenValue.replace("\n", ";");
                }
                payload[tokenName] = tokenValue
            }
        });

        service.request(
            "configs/conf-inputs/duplicity%3A%2F%2Fbackup",
            "POST",
            null,
            null,
            payload,
            {"Content-Type": "application/json"},
            null
        );
    });
});
