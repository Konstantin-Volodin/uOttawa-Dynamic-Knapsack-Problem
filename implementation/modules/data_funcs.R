library(tidyverse)
library(here)

# Generate Summary From Patient Level Data
generate_summary <- function(path, modif, dur, warm, repl) {
  
  # Data
  data <- read_data(path, modif)
  
  # Generate Wait Time
  avg_pw <- analyse_wait(data, dur, warm, repl)
  # Generate Wait List
  avg_wtl <- analyse_wait_list(data, dur, warm, repl)
  # Generate Utilization
  avg_util <- analyse_util(data, dur, warm, repl)
  # Generate Reschedules
  avg_rsc <- analyse_resch(data, dur, warm, repl)
  # Generate Transitions
  avg_tr <- analyse_trans(data, dur, warm, repl)
  
  results <- list(
    'data' = data,
    'results' = list(
      'pw' = avg_pw, 
      'wtl' = avg_wtl, 
      'util' = avg_util, 
      'rsc' = avg_rsc,
      'tr' = avg_tr
    )
  )
  
  return (results)
}
### Reads all relevant data
read_data <- function(path, modif) {
  modif_val <- as.numeric(strsplit(modif, '-')[[1]][2])
  
  # Patient Transition Data
  state_my <- read_csv(here(path,'res','state', paste0('full-sm-res-my-',modif,'.txt')), 
                       col_types = cols(id = col_double(), repl=col_double(), period=col_double(), 
                                        arrived_on=col_double(), sched_to=col_double(), 
                                        resch_from=col_double(), resch_to=col_double())) %>% 
    filter(!is.na(id))
  state_md <- read_csv(here(path,'res','state', paste0('full-sm-res-mdp-',modif,'.txt')), 
                       col_types = cols(id = col_double(), repl=col_double(), period=col_double(),
                                        arrived_on=col_double(), sched_to=col_double(), 
                                        resch_from=col_double(), resch_to=col_double())) %>% 
    filter(!is.na(id))
  state <- bind_rows(state_my, state_md)
  
  # Cost Data
  cost_my <- read_csv(here(path,'res','cost',paste0('full-sm-res-my-',modif,'.txt'))) %>% mutate(policy = 'myopic')
  cost_md <- read_csv(here(path,'res','cost',paste0('full-sm-res-mdp-',modif,'.txt'))) %>% mutate(policy = 'MDP')
  cost <- bind_rows(cost_my, cost_md)

  # Utilization Data
  util_my <- read_csv(here(path,'res','util',paste0('full-sm-res-my-',modif,'.txt'))) %>% mutate(policy = 'myopic') %>% filter(horizon_period == 0)
  util_md <- read_csv(here(path,'res','util',paste0('full-sm-res-mdp-',modif,'.txt'))) %>% mutate(policy = 'MDP') %>% filter(horizon_period == 0)
  util <- bind_rows(util_my, util_md) %>%
    mutate(bed = usage_admin/1.5, OR = usage_OR/(modif_val*11.25)) %>%
    select(repl, period, policy, bed, OR) %>%
    pivot_longer(cols = c('bed','OR'), names_to='resource', values_to = 'util')

  # Logging Data
  log_my <- read_csv(here(path,'res','sa',paste0('full-sm-res-my-',modif,'.txt')), 
                     col_types = cols(period=col_double(),`state-aciton`=col_character(),
                                      value=col_character(),t=col_double(),tp=col_double(),
                                      m=col_double(),val=col_double())) %>% 
    rename(st_ac = `state-aciton`) %>% mutate(policy = "myopic")
  log_md <- read_csv(here(path,'res','sa',paste0('full-sm-res-mdp-',modif,'.txt')), 
                     col_types = cols(period=col_double(),`state-aciton`=col_character(),
                                      value=col_character(),t=col_double(),tp=col_double(),
                                      m=col_double(),val=col_double())) %>% 
    rename(st_ac = `state-aciton`) %>% mutate(policy = 'MDP')
  log <- bind_rows(log_my, log_md)

  return(
    list('state' = state, 'cost' = cost, 'util' = util, 'log' = log)
  )
  
}
### Analyses Wait Time
analyse_wait <- function(data, dur, warm, repl) {
  state <- data$state
  
  # Post warm-up wait time (including not completed)
  pwu_arr_nc <- state %>%
    group_by(policy, repl, id) %>% 
    filter(action %in% c('arrived','scheduled', 'rescheduled')) %>% 
    slice(c(1,n())) %>%
    mutate(final_sched = case_when(
      is.na(sched_to) == F ~ sched_to,
      is.na(resch_to) == F ~ resch_to,
      TRUE ~ dur+1
    )) %>%
    mutate(final_sched = min(final_sched, na.rm=T)) %>%
    slice(c(1)) %>% ungroup() %>%
    select(policy, repl, period, id, priority, complexity, surgery, arrived_on, final_sched) %>%
    mutate(wait = final_sched - arrived_on)

  # Average wait time
  pw_avg <- pwu_arr_nc %>%
    filter(period > warm) %>% group_by(policy) %>%
    summarize(w_m = mean(wait), w_sd = sd(wait)) %>%
    mutate(w_moe = 1.96 * w_sd / sqrt(repl)) %>%
    mutate(surgery = 'overall')
  
  # Surgery wait time
  pw_srg <- pwu_arr_nc %>% 
    filter(period > warm) %>% group_by(policy, surgery) %>%
    summarize(w_m = mean(wait), w_sd = sd(wait)) %>%
    mutate(w_moe = 1.96 * w_sd / sqrt(repl))  
  
  # Wait time data
  pw <- bind_rows(pw_avg, pw_srg) %>% 
    select(policy, surgery, w_m, w_moe) %>%
    mutate(surgery = case_when(
      surgery == 'overall' ~ "Overall",
      surgery == "1. SPINE POSTERIOR DECOMPRESSION/LAMINECTOMY LUMBAR" ~ "Surgery1",
      surgery == "4. SPINE POST CERV DECOMPRESSION AND FUSION W INSTR" ~ "Surgery4",
      surgery == "6. SPINE POSTERIOR DISCECTOMY LUMBAR" ~ "Surgery6"
    )) %>%
    mutate(val = paste0(round(w_m,2), " += ", round(w_moe,2))) %>%
    select(policy, surgery, val) %>% 
    pivot_wider(names_from = surgery, values_from = val)
  
  return(pw)
  #graphs
  # bx_wait_c <- ggplot(pwu_wait_c %>% right_join(pwu_pat) %>% drop_na()) +
  #   geom_boxplot(aes(y=wait, x=surgery, fill=policy)) +
  #   facet_grid(complexity ~ priority)
  # bx_wait_nc <- ggplot(pwu_wait_nc %>% right_join(pwu_pat)) +
  #   geom_boxplot(aes(y=wait, x=surgery, fill=policy)) +
  #   facet_grid(complexity ~ priority)
  # 
  # pwu_wait_nc %>% filter(period > warmup) %>%
  #   group_by(policy, surgery) %>%
  #   summarize(w_m = mean(wait), w_sd = sd(wait)) %>%
  #   mutate(w_me = 1.96 * w_sd / sqrt(30)) %>% select(-c(w_sd))
  # pwu_wait_nc %>% filter(period > warmup) %>%
  #   group_by(policy) %>%
  #   summarize(w_m = mean(wait), w_sd = sd(wait)) %>%
  #   mutate(w_me = 1.96 * w_sd / sqrt(30)) %>% select(-c(w_sd))
  # 
}
### Analyses Wait List
analyse_wait_list <- function(data, dur, warm, repl) {
  log <- data$log
  
  # Post-warmup waitlist
  pwu_wtl <- bind_rows(
    data$log %>% filter(st_ac == 'post-state' & value == 'psp' & t > 1),
    data$log %>% filter(st_ac == 'post-state' & value == 'pwp')
  ) %>% group_by(policy, repl, period, c) %>%
    summarize(wl = sum(val)) %>% ungroup() %>%
    complete(policy, repl, c, period) %>%
    replace_na(list(wl = 0)) %>%
    rename(surgery = c) %>%
    filter(period > warm)

  # Average wait list
  wtl_avg <- pwu_wtl %>% 
    group_by(policy, repl, period) %>%
    summarize(wl_t = sum(wl)) %>%
    group_by(policy) %>%
    summarize(wl_m = mean(wl_t), wl_sd = sd(wl_t)) %>%
    mutate(wl_moe = 1.96 * wl_sd / sqrt(repl)) %>%
    mutate(surgery = 'overall')
  
  # Surgery wait list
  wtl_srg <- pwu_wtl %>% 
    group_by(policy, surgery) %>%
    summarize(wl_m = mean(wl), wl_sd = sd(wl)) %>%
    mutate(wl_moe = 1.96 * wl_sd / sqrt(repl))
  
  # Wait List Data
  wtl <- bind_rows(wtl_avg, wtl_srg) %>% 
    select(policy, surgery, wl_m, wl_moe) %>%
    mutate(surgery = case_when(
      surgery == 'overall' ~ "Overall",
      surgery == "1. SPINE POSTERIOR DECOMPRESSION/LAMINECTOMY LUMBAR" ~ "Surgery1",
      surgery == "4. SPINE POST CERV DECOMPRESSION AND FUSION W INSTR" ~ "Surgery4",
      surgery == "6. SPINE POSTERIOR DISCECTOMY LUMBAR" ~ "Surgery6"
    )) %>%
    mutate(val = paste0(round(wl_m,2), " += ", round(wl_moe,2))) %>%
    select(policy, surgery, val) %>% 
    pivot_wider(names_from = surgery, values_from = val)
  
  return(wtl)
  
}
### Analyses Utilization
analyse_util <- function(data, dur, warm, repl) {
  # Utilization
  util <- data$util
  
  # Average Utilization
  util_m <- util %>%
    filter(period > warm) %>%
    group_by(policy, resource) %>%
    summarize(ut_m = mean(util)*100, ut_sd = sd(util)*100) %>%
    mutate(ut_moe = 1.96 * ut_sd / sqrt(repl)) %>% 
    mutate(val = paste0(round(ut_m,2), " += ", round(ut_moe,2))) %>%
    select(policy, resource, val) %>%
    pivot_wider(names_from = resource, values_from = val)
  
  return(util_m)
  
  # bx_util_p <- ggplot(util %>% filter(period > warmup)) +
  #   geom_boxplot(aes(y=util, x=resource, fill=policy)) +
  #   theme_minimal()
  # util %>% filter(period > warmup) %>%
  #   group_by(policy, resource) %>%
  #   summarize(util_m = mean(util), util_sd = sd(util)) %>%
  #   mutate(util_me = 1.96 * util_sd / sqrt(30))
}
### Analysis of reschedules
analyse_resch <- function(data, dur, warm, repl) {
  state <- data$state
  
  # Post Warm Up Reschedules
  pwu_rsc <- state %>% 
    filter(action == 'rescheduled')  %>%
    group_by(policy,surgery,repl,period) %>%
    summarize(resch=n()) %>% 
    ungroup() %>%
    complete(policy, surgery, repl, period=seq(dur)) %>%
    replace_na(list(resch = 0)) %>%
    filter(period > warm)
  
  # Total Surgery Reschedules
  rst_srg <- pwu_rsc %>%
    group_by(policy, repl, surgery) %>%
    summarize(rs_t = sum(resch)) %>% ungroup()
  
  # Total Surgery Arrivals
  arr_srg <- state %>% 
    filter(action == 'arrived') %>%
    filter(arrived_on > warm) %>%
    group_by(policy, repl, surgery) %>%
    summarize(ar_t = n()) %>% ungroup()
  
  # Average reschedules
  rsp_avg <- (rst_srg %>% group_by(policy, repl) %>% summarize(rs_t = sum(rs_t))) %>%
    full_join(arr_srg %>% group_by(policy, repl) %>% summarize(ar_t = sum(ar_t))) %>%
    mutate(rsp = rs_t / ar_t) %>%
    group_by(policy) %>%
    summarize(rsp_m = mean(rsp)*100, rsp_sd = sd(rsp)*100) %>%
    mutate(rsp_moe = 1.96 * rsp_sd / sqrt(repl)) %>%
    mutate(surgery = 'overall')
  
  # Surgery reschedules
  rsp_srg <- rst_srg %>%
    full_join(arr_srg) %>%
    mutate(rsp = rs_t / ar_t) %>%
    group_by(policy, surgery) %>%
    summarize(rsp_m = mean(rsp)*100, rsp_sd = sd(rsp)*100) %>%
    mutate(rsp_moe = 1.96 * rsp_sd / sqrt(repl)) %>%
    replace_na(list(rsp_m = 0, rsp_sd = 0))
  
  # Reschedules Data
  rsp <- bind_rows(rsp_avg, rsp_srg) %>%
    select(policy, surgery, rsp_m, rsp_moe) %>%
    mutate(surgery = case_when(
      surgery == 'overall' ~ "Overall",
      surgery == "1. SPINE POSTERIOR DECOMPRESSION/LAMINECTOMY LUMBAR" ~ "Surgery1",
      surgery == "4. SPINE POST CERV DECOMPRESSION AND FUSION W INSTR" ~ "Surgery4",
      surgery == "6. SPINE POSTERIOR DISCECTOMY LUMBAR" ~ "Surgery6"
    )) %>%
    mutate(val = paste0(round(rsp_m,2), " += ", round(rsp_moe,2))) %>%
    select(policy, surgery, val) %>% 
    pivot_wider(names_from = surgery, values_from = val)
  
  return(rsp)
}
### Analysis of transitions
analyse_trans <- function(data, dur, warm, repl) {
  state <- data$state
  
  # Post Warm Up Reschedules
  pwu_tr <- state %>% 
    filter(action == 'transition')  %>%
    group_by(policy,surgery,repl,period) %>%
    summarize(tr=n()) %>% 
    ungroup() %>%
    complete(policy, surgery, repl, period=seq(dur)) %>%
    replace_na(list(tr = 0)) %>%
    filter(period > warm)
  
  # Total Surgery Transitions
  trt_srg <- pwu_tr %>%
    group_by(policy, repl, surgery) %>%
    summarize(tr_t = sum(tr)) %>% ungroup()
  
  # Total Surgery Arrivals
  arr_srg <- state %>% 
    filter(action == 'arrived') %>%
    filter(arrived_on > warm) %>%
    group_by(policy, repl, surgery) %>%
    summarize(ar_t = n()) %>% ungroup()
  
  # Average transitions
  trp_avg <- (trt_srg %>% group_by(policy, repl) %>% summarize(tr_t = sum(tr_t))) %>%
    full_join(arr_srg %>% group_by(policy, repl) %>% summarize(ar_t = sum(ar_t))) %>%
    mutate(trp = tr_t / ar_t) %>%
    group_by(policy) %>%
    summarize(trp_m = mean(trp)*100, trp_sd = sd(trp)*100) %>%
    mutate(trp_moe = 1.96 * trp_sd / sqrt(repl)) %>%
    mutate(surgery = 'overall')
  
  # Surgery reschedules
  trp_srg <- trt_srg %>%
    full_join(arr_srg) %>%
    mutate(trp = tr_t / ar_t) %>%
    group_by(policy, surgery) %>%
    summarize(trp_m = mean(trp)*100, trp_sd = sd(trp)*100) %>%
    mutate(trp_moe = 1.96 * trp_sd / sqrt(repl)) %>%
    replace_na(list(trp_m = 0, trp_sd = 0))
  
  # Reschedules Data
  trp <- bind_rows(trp_avg, trp_srg) %>%
    select(policy, surgery, trp_m, trp_moe) %>%
    mutate(surgery = case_when(
      surgery == 'overall' ~ "Overall",
      surgery == "1. SPINE POSTERIOR DECOMPRESSION/LAMINECTOMY LUMBAR" ~ "Surgery1",
      surgery == "4. SPINE POST CERV DECOMPRESSION AND FUSION W INSTR" ~ "Surgery4",
      surgery == "6. SPINE POSTERIOR DISCECTOMY LUMBAR" ~ "Surgery6"
    )) %>%
    mutate(val = paste0(round(trp_m,2), " += ", round(trp_moe,2))) %>%
    select(policy, surgery, val) %>% 
    pivot_wider(names_from = surgery, values_from = val)
  
  return(trp)
}



# Generate Summary From State-Action Data
generate_summary_sa <- function(path, modif, dur, warm, repl) {
  dat_my <- read_csv(here(path,'res','sa', paste0('full-sm-res-my-',modif,'.txt'))) %>% mutate(policy='my')
  dat_md <- read_csv(here(path,'res','sa', paste0('full-sm-res-mdp-',modif,'.txt'))) %>% mutate(policy='md')
  dat <- bind_rows(dat_my, dat_md)
  
  # Scheduling
  sched_dat <- dat %>% filter(`state-aciton` == 'action' & value == 'sc') %>%
    filter(period >= warm) %>%
    mutate(t = as.numeric(t)) %>%
    group_by(repl, policy, t, c, d) %>% 
    summarize(count = sum(val)) %>% 
    group_by(policy, t,c,d) %>%
    summarize(mean = mean(count), sd = sd(count)) %>%
    mutate(mean_log = log(mean)) %>%
    separate(c, sep=" ", into=c('c')) %>%
    mutate(c = paste0('S',c))
  
  sched_plt <- ggplot(sched_dat) +
    geom_bar(aes(x=t, y=mean, fill=c), stat='identity') +
    geom_text(aes(x=t, y=mean, label=round(mean,1)), size=2) +
    facet_grid(c+d ~ policy, scales="fixed") + 
    labs(x='Time (Week)', y='Count (Sched)', title='Scheduling Numbers')
  
  # Rescheduling
  rsc_dat <- dat %>% filter(value == 'rsc') %>%
    filter(period >= warm) %>%
    group_by(policy, repl, c, d,t ,tp) %>%
    summarize(avg = sum(val)) %>%
    group_by(policy, c, d, t, tp) %>%
    summarize(mean = mean(avg), sd = sd(avg)) %>%
    separate(c, sep=' ', into=c('c')) %>%
    mutate(gb = ifelse(tp==1, 'Good','Bad'))
  
  
  rsc_plt <- ggplot(rsc_dat) +
    geom_bar(aes(x=t, y=mean, fill=tp), stat = 'identity', position='stack') +
    facet_grid(c+d ~ gb+policy, scales='free') + 
    labs(x='Time (Week)', y='Count (Sched)', title='Reschedules per Group')
  
  
  
  # Waitlist
  waitlist_dat <- dat %>% filter(value == 'pw') %>%
    filter(period >= warm) %>%
    group_by(policy, repl, c, d, m) %>% 
    summarize(avg = sum(val)) %>% 
    group_by(policy, c,d, m) %>%
    summarize(mean = mean(avg), sd = sd(avg)) %>%
    separate(c, sep=" ", into=c('c'))
  
  wtl_plt <- ggplot(waitlist_dat) +
    geom_bar(aes(x=m, y=mean, fill=c), stat = 'identity') +
    geom_text(aes(x=m, y=mean, label=round(mean,1)), size=2) +
    facet_grid(c+d ~ policy, scales='free') + 
    labs(x='Time (Week)', y='Count (Sched)', title='Waitlist Size by Group')
  
  return( list(
    'data' = dat,
    'res_data' = list(
      'sched_data' = sched_dat,
      'rsc_data' = rsc_dat,
      'waitlist_data' = waitlist_dat
    ),
    'res_plot' = list(
      'sched_plt' = sched_plt,
      'rsc_plt' = rsc_plt,
      'waitlist_plt' = wtl_plt
    )
  ))
}



# Generate Policy From Z-Scores
generate_summary_zs <- function(path, modif, cuu) {
  # # Generate Data
  # generate_z_score(path, modif, TRUE, cuu)
  # generate_z_score(path, modif, FALSE, cuu)
  
  # Read Data
  dat_my <- read_csv(here(path,'res','z_fact', paste0('full-sm-res-my-',modif,'.csv'))) %>% mutate(policy='myopic')
  dat_md <- read_csv(here(path,'res','z_fact', paste0('full-sm-res-mdp-',modif,'.csv'))) %>% mutate(policy='mdp')
  dat <- bind_rows(dat_my, dat_md)
  
  # Clean Up
  dat <- dat %>% 
    pivot_longer(cols = c('Val', 'Val_Adj'), names_to='Type', values_to='Val') %>%
    mutate(Type = case_when(Type == 'Val' ~ 'Norm', Type == 'Val_Adj' ~ 'Adjusted',))
  
  # Create Plots
  zf_plt <- ggplot(dat %>% filter(M == 0),
                          aes(x=T, y=Val, color=C, linetype=D, shape=D)) +
    geom_line() + geom_point() + 
    facet_grid(Type ~ policy) + 
    theme_minimal()

  return(list(
    'data' = dat,
    'zf_plt' = zf_plt
  ))
}
