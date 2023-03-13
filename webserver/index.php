<html>
<head>
    <title>Doortron</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="30">

    <style>
        p {
            width: 100%;
            text-align: center;
            margin-top: 0;
            margin-bottom: 0;
            color: white;
            opacity: 0.8;
            font-family: sans-serif;
        }

        .top-text {
            font-weight: bold;
            margin-bottom: 15pt;
            font-size: 35pt;
        }

        .bot-text {
            font-weight: bold;
            margin-bottom: 15pt;
            font-size: 65pt;
        }

        .time-text {
            margin-bottom: 15pt;
            font-size: 15pt;
        }

        .info-text {
            margin-bottom: 15pt;
            font-size: 15pt;
        }
    </style>
<?php
$statusfile = fopen("/tmp/doortron_dont_touch", "r");
$status = 2;
$updated = 0;

if ($statusfile == false) {
    $status = 2;
    $updated = 0;
} else {
    fscanf($statusfile, "%d %d", $status, $updated);
    fclose($statusfile);
}

if ((time() - $updated) > 600) {
    $status = 2;
}

?>
</head>

<?php
if ($status == 0) {
    print '<body style="background-color: #8b0000;">';
} else if ($status == 1) {
    print '<body style="background-color: #006400;">';
} else {
    print '<body style="background-color: #444444;">';
}
?>
    <div>
        <p class="top-text">
            <?php
if (($status == 0) or ($status == 1)) {
    print "Roboclub is...";
} else {
    print "";
}
            ?>
        </p>
        <p class="bot-text">
            <?php
if ($status == 0) {
    print "CLOSED";
} else if ($status == 1) {
    print "OPEN";
} else {
    print "";
}
            ?>
        </p>
        <p class="time-text">
            <?php
if (($status == 0) or ($status == 1)) {
    print "(last updated ";
    print date("g:i A, M j", $updated);
    print ")";
} else {
    print "";
}
            ?>
        </p>
        <p class="info-text">
            <?php
if ($status == 0) {
    print "Contact an officer if you would like to get into the club.";
} else if ($status == 1) {
    print "This means there's an officer at the club, feel free to drop by :)";
} else {
    print "<b>The DoorTron system is currently offline, if this persists for more than 5 minutes please notify an officer</b>";
}
            ?>

        </p>
    </div>
</body>
</html>
