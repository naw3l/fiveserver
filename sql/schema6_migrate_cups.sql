-- Migration: add cup/tournament support + friends/inbox features to an
-- existing sixserver database
-- Run this once against your existing sixserver DB if you set it up
-- before cup support was added.

ALTER TABLE profiles
    ADD COLUMN competition_gold smallint unsigned not null default 0,
    ADD COLUMN competition_silver smallint unsigned not null default 0,
    ADD COLUMN winnerscup_gold smallint unsigned not null default 0,
    ADD COLUMN winnerscup_silver smallint unsigned not null default 0;

create table if not exists cups (
    id int unsigned not null auto_increment,
    name varchar(64) not null,
    cup_type enum('competition','winnerscup') not null default 'winnerscup',
    status enum('open','active','finished') not null default 'open',
    created_on timestamp not null default current_timestamp,
    finished_on datetime default null,
    primary key(id)
) Engine=InnoDB default charset=utf8;

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
