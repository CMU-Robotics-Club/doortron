<html>
<head>
    <title>Doortron</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="30">

    <style>
        .text {
            text-align: center;
            margin-top: 0;
            margin-bottom: 0;
            color: white;
            opacity: 0.8;
            font-family: sans-serif;
            font-weight: bold;
            margin-bottom: 15pt;
            font-size: 65pt;
        }

        .wrap {
            width: 100%;
            overflow: hidden;
        }

        body {
            margin: 0;
            padding: 0;
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

<body>
<div style="text-align: center;">
<?php 
if ($status == 0) {
    $svg = file_get_contents("closed.svg");
} else if ($status == 1) {
    $svg = file_get_contents("open.svg");
} else {
    $svg = file_get_contents("unknown.svg");
}
$position = strpos($svg, "<svg");
$svg = substr($svg, $position);
$updated_str = date("g:i A, M j", $updated);
$svg = str_replace("__TIMESTAMP__", $updated_str, $svg);
print $svg;

?>
</div>
</body>
</html>

<!-- <iframe class="widget-frame" src="https://api.codetabs.com/v1/proxy/?quest=http://roboclubx.roboclub.org/doortron/widget.php" style="border: none; width: 100%;"></iframe> -->
