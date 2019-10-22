require([
    "underscore",
    "jquery",
    "splunkjs/mvc/searchmanager",
    "splunkjs/mvc",
    "splunkjs/ready!",
    "splunkjs/mvc/simplexml/ready!",
], function(_, $, SearchManager, mvc) {
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

        setToken("target_url", config.target_url)
    });

    $("body").on("click", ".save-button", function(e) {
        setToken("restorePath", $("input[data-token=dest]")[0].value);

        $("#dupRestoreWrapper").html(
            "<h1>Restoring " + defaultTokenModel.get("filename") + " to " + defaultTokenModel.get("restorePath") + "</h1>"
        );

        // $(".save-button")[0].disable();
        // $(".cancel-button")[0].disable();

        var dupRestoreSearchId = _.uniqueId("DuplicityRestore_");
        var dupRestoreSearch = new SearchManager({
            id: dupRestoreSearchId,
            autostart: false,
            search: '| duplicity restore --time=$epochBackupStartTime|n$ --file-to-restore $filename$ $target_url$ $restorePath$'
        }, {"tokens": true});

        // var tbl = TableView({
        //     "wrapper_id": "dupRestoreWrapper",
        //     "table_id": "dupRestore",
        //     "search_id": dupRestoreSearchId,
        //     "title": "foo",
        // });

        dupRestoreSearch.startSearch();

        dupRestoreSearch.on("search:done", function(e) {
            unsetToken("filename");
            unsetToken("restoreFilename");
            unsetToken("restorePath");

            if (e.content.messages.length > 0) {
                console.log(e.content.messages[0]);
                setToken("restoreFailed", e.content.messages[0].text);
            } else {
                setToken("restoreDone", "yes");
            }
        })

        dupRestoreSearch.on("search:start", function(e) {
            console.log(e.content.request.search);
        })

        // dupRestoreSearch.on("all", function(e) {
        //     console.log(e);
        // })
        // tbl.render();
    });

    $("body").on("click", ".cancel-button", function(e) {
        unsetToken("filename");
        unsetToken("restoreFilename");
        unsetToken("restorePath");
    });

    $("body").on("click", ".done-button", function(e) {
        unsetToken("filename");
        unsetToken("restoreFilename");
        unsetToken("restorePath");
        unsetToken("restoreFailed");
        unsetToken("restoreDone");
    });
});
