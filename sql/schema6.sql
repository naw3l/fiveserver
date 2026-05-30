create table if not exists users (
    id int unsigned not null auto_increment,
    deleted boolean not null default 0,
    username varchar(32) not null unique,
    serial char(20) not null,
    hash char(32) not null unique,
    reset_nonce varchar(32) default null,
    updated_on timestamp not null default current_timestamp on update current_timestamp,
    primary key(id)
    
) Engine=InnoDB default charset=utf8;

create table if not exists profiles (
    id int unsigned not null auto_increment,
    deleted boolean not null default 0,
    user_id int unsigned not null,
    ordinal tinyint not null default -1,
    name varchar(32) not null unique,
    `rank` int unsigned not null default 0,
    rating int unsigned not null default 0,
    points int unsigned not null default 0,
    disconnects int unsigned not null default 0,
    updated_on timestamp not null default current_timestamp on update current_timestamp,
    seconds_played bigint unsigned not null default 0,
    comment varchar(256) default null,
    competition_gold smallint unsigned not null default 0,
    competition_silver smallint unsigned not null default 0,
    winnerscup_gold smallint unsigned not null default 0,
    winnerscup_silver smallint unsigned not null default 0,
    primary key(id),
    foreign key(user_id) references users (id)

) Engine=InnoDB default charset=utf8;

create table if not exists matches (
    id bigint unsigned not null auto_increment,
    score_home int unsigned not null default 0,
    score_away int unsigned not null default 0,
    team_id_home int not null default -1,
    team_id_away int not null default -1,
    played_on timestamp not null default current_timestamp,
    primary key(id)

) Engine=InnoDB default charset=utf8;

create table if not exists matches_played (
    id bigint unsigned not null auto_increment,
    match_id bigint unsigned not null,
    profile_id int unsigned not null,
    home boolean not null default 0,
    primary key(id),
    unique key(match_id, profile_id),
    foreign key(match_id) references matches (id),
    foreign key(profile_id) references profiles (id)

) Engine=InnoDB default charset=utf8;

create table if not exists streaks (
    id bigint unsigned not null auto_increment,
    profile_id int unsigned not null,
    wins int unsigned not null default 0,
    best int unsigned not null default 0,
    primary key(id),
    unique key(profile_id),
    foreign key(profile_id) references profiles (id)

) Engine=InnoDB default charset=utf8;

create table if not exists friends (
    id bigint unsigned not null auto_increment,
    profile_id int unsigned not null,
    friend_profile_id int unsigned not null,
    primary key(id),
    unique key(profile_id, friend_profile_id),
    foreign key(profile_id) references profiles (id),
    foreign key(friend_profile_id) references profiles (id)

) Engine=InnoDB default charset=utf8;

create table if not exists blocked (
    id bigint unsigned not null auto_increment,
    profile_id int unsigned not null,
    blocked_profile_id int unsigned not null,
    primary key(id),
    unique key(profile_id, blocked_profile_id),
    foreign key(profile_id) references profiles (id),
    foreign key(blocked_profile_id) references profiles (id)

) Engine=InnoDB default charset=utf8;

create table if not exists settings (
    id bigint unsigned not null auto_increment,
    profile_id int unsigned not null,
    settings1 blob default null,
    settings2 blob default null,
    primary key(id),
    unique key(profile_id),
    foreign key(profile_id) references profiles (id)

) Engine=InnoDB default charset=utf8;

-- Cup/Tournament tables
-- cup_type: 'competition' (league) or 'winnerscup' (knockout)
-- status: 'open' (accepting participants), 'active' (in progress), 'finished'
create table if not exists cups (
    id int unsigned not null auto_increment,
    name varchar(64) not null,
    cup_type enum('competition','winnerscup') not null default 'winnerscup',
    status enum('open','active','finished') not null default 'open',
    created_on timestamp not null default current_timestamp,
    finished_on datetime default null,
    primary key(id)

) Engine=InnoDB default charset=utf8;

-- Participants enrolled in a cup
create table if not exists cup_participants (
    id int unsigned not null auto_increment,
    cup_id int unsigned not null,
    profile_id int unsigned not null,
    status enum('active','eliminated','winner','runner_up') not null default 'active',
    primary key(id),
    unique key(cup_id, profile_id),
    foreign key(cup_id) references cups (id),
    foreign key(profile_id) references profiles (id)

) Engine=InnoDB default charset=utf8;

-- Individual cup match pairings within a cup bracket
-- round: 1=final, 2=semis, 4=quarters, 8=round of 16, etc.
-- match_id links to the actual played match when completed
create table if not exists cup_matches (
    id int unsigned not null auto_increment,
    cup_id int unsigned not null,
    match_id bigint unsigned default null,
    round int unsigned not null default 1,
    home_profile_id int unsigned not null,
    away_profile_id int unsigned not null,
    winner_profile_id int unsigned default null,
    status enum('pending','completed','walkover') not null default 'pending',
    played_on datetime default null,
    primary key(id),
    foreign key(cup_id) references cups (id),
    foreign key(match_id) references matches (id),
    foreign key(home_profile_id) references profiles (id),
    foreign key(away_profile_id) references profiles (id),
    foreign key(winner_profile_id) references profiles (id)

) Engine=InnoDB default charset=utf8;


create table if not exists messages (
    id bigint unsigned not null auto_increment,
    to_profile_id int unsigned not null,
    from_profile_id int unsigned default null,
    subject varchar(64) not null default '',
    body varchar(512) not null default '',
    read_flag boolean not null default 0,
    sent_on timestamp not null default current_timestamp,
    primary key(id),
    foreign key(to_profile_id) references profiles (id),
    foreign key(from_profile_id) references profiles (id)

) Engine=InnoDB default charset=utf8;

