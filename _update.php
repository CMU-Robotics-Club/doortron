<?php

if (hash("sha256", $_GET["key"]) == "[removed for security reasons]") {
    // nya~
    $status = 2;
    if ($_GET["status"] == "1") {
        $status = 1;
    } else if ($_GET["status"] == "0") {
        $status = 0;
    }

    $statusfile = fopen("/tmp/doortron_dont_touch", "w+") or die("ERROR");
    fprintf($statusfile, "%d %d", $status, time());
    fclose($statusfile);
    print "OK";
} else {
    print "Go away";
}

?>
